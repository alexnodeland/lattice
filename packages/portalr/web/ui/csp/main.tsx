/**
 * The page the CSP tests drive: ui's Markdown and a dashboard, built as app and admin are, and
 * served with the Content-Security-Policy both UIs share (`policy.txt`), so whatever it renders
 * meets it. What it draws its address names, from the page's own tasks, as the UIs draw (portalr
 * ADR-0047): `?markdown=` the Markdown given, whole, or with `&stream` a character at a time, as an
 * agent's run writes it, with the integrations `&on=` and `&off=` name, such as `markdown:math`,
 * switched so and the rest their defaults, and on the root `data-drawn` once it is whole, or
 * `data-error` if it stopped; `?dashboard` the dashboard gallery; `?eval` an evaluated string; and
 * `?app=` a mini app of that HTML, run in the sandbox at `&apps=` (portalr ADR-0051); and `?diagram`
 * the app's card of a diagram, whose canvas the test opens (portalr ADR-0072); `?diagram=edit`
 * one the test may edit, through a host of the page's own, which keeps what it is sent on
 * `window.canvasSent` (portalr ADR-0074).
 */

import type { IntegrationKey } from "@portalr/client";
import "../src/styles.css";
import { useState } from "react";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";
// The app's diagram card and its canvas add-on, built as app's build builds them (portalr ADR-0072).
import { diagram } from "../../app/src/diagram";
import { type CanvasHost, CanvasHostContext } from "../../app/src/on-demand/canvas-host";
import type { Heard } from "../../app/src/on-demand/presence";
import { AppHostContext, DashboardView, IntegrationsContext, Markdown } from "../src";
import { AppFrame } from "../src/app-frame";
import { ShownContext } from "../src/artifacts";
import { byDefault } from "../src/integrations";
import { SUPPORT } from "../src/test/dashboards";
import SAMPLE from "./diagram.json";

/** The characters a stream renders, one at a time, before it yields. */
const STEP = 25;

const root = createRoot(document.getElementById("root") as HTMLElement);
const asked = new URLSearchParams(location.search);

const text = asked.get("markdown");
if (text !== null) {
  const named = (list: string) => new Set((asked.get(list) ?? "").split(",").filter(Boolean));
  const [on, off] = [named("on"), named("off")];
  const isEnabled = (key: IntegrationKey) => on.has(key) || (!off.has(key) && byDefault(key));
  const show = (shown: string, streaming: boolean) =>
    flushSync(() =>
      root.render(
        <IntegrationsContext value={isEnabled}>
          <Markdown streaming={streaming}>{shown}</Markdown>
        </IntegrationsContext>,
      ),
    );
  // Said on the root once the text is drawn whole, which a test waits for.
  const drawn = () => {
    show(text, false);
    document.documentElement.dataset.drawn = "whole";
  };
  if (asked.has("stream")) {
    // A character at a time, each its own render, as a stream's frames arrive, from the page's
    // own tasks once it has loaded, so a navigation isn't held up by it. It yields every few
    // characters, as a stream does between frames, and says how far it has come on the root
    // (`data-streamed`), so a test waits on its progress rather than on a guess at its time.
    let end = 1;
    const stream = () => {
      try {
        for (const until = Math.min(end + STEP, text.length); end < until; end += 1) {
          show(text.slice(0, end), true);
        }
        document.documentElement.dataset.streamed = String(end);
        if (end < text.length) {
          setTimeout(stream);
          return;
        }
        drawn();
      } catch (error) {
        // Why it stopped, which a test that waits for `data-drawn` says.
        document.documentElement.dataset.error = String(error);
        throw error;
      }
    };
    addEventListener("load", () => setTimeout(stream));
  } else {
    drawn();
  }
}
if (asked.has("eval")) {
  // What the policy refuses from the page's own task, which a test's evaluate would pass.
  try {
    Function("return 1")();
  } catch {
    // Refused, as it should be: the violation is what the test reads.
  }
}
if (asked.has("dashboard")) {
  flushSync(() => root.render(<DashboardView dashboard={SUPPORT} />));
}
const html = asked.get("app");
if (html !== null) {
  const done = async () => ({ outcome: "done" as const });
  const host = { origin: asked.get("apps"), setState: done, submit: done };
  flushSync(() =>
    root.render(
      <IntegrationsContext value={() => true}>
        <AppHostContext value={host}>
          <AppFrame
            app={{ title: "Probe", summary: "Tries every way out.", html, state: {} }}
            shown={{ id: "app_1", version: 1 }}
          />
        </AppHostContext>
      </IntegrationsContext>,
    ),
  );
}
/** What a hostile hand could write in a diagram: links, embedded pages, an image. */
const HOSTILE = {
  name: "Hostile",
  elements: {
    ...SAMPLE.elements,
    linked: {
      id: "linked",
      type: "rectangle",
      x: 0,
      y: 200,
      width: 200,
      height: 80,
      link: "https://example.com/",
    },
    framed: {
      id: "framed",
      type: "embeddable",
      x: 300,
      y: 200,
      width: 400,
      height: 300,
      link: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    },
    iframe: {
      id: "iframe",
      type: "iframe",
      x: 0,
      y: 600,
      width: 400,
      height: 300,
      link: "https://example.com/",
    },
    pictured: {
      id: "pictured",
      type: "image",
      x: 800,
      y: 0,
      width: 100,
      height: 100,
      fileId: "nope",
      status: "saved",
    },
  },
  files: {},
};

/** What no canvas could draw as given: numbers that aren't, an arrow with no points. */
const BROKEN = {
  name: "Broken",
  elements: {
    a: { id: "a", type: "arrow", x: "far", y: null, points: "none", width: -1 },
    b: { id: "b", type: "text", text: 7, fontSize: "big", containerId: 3 },
    c: { id: "c", type: "rectangle", x: 1e308, y: -1e308, width: 1e308, height: 1e308, angle: "x" },
    d: {
      id: "d",
      type: "line",
      points: [
        [0, 0],
        ["x", null],
      ],
    },
    e: { type: "ellipse" },
  },
  files: {},
};

const DIAGRAMS: Record<string, object> = {
  "": SAMPLE,
  edit: SAMPLE,
  hostile: HOSTILE,
  broken: BROKEN,
};

declare global {
  interface Window {
    canvasSent: { commits: unknown[]; uploads: string[]; said: unknown[] };
    /** Tell the canvas who else is there, as its connection would. */
    canvasHeard: (heard: Heard) => void;
    /** A newer revision of the diagram, as the page would read it. */
    canvasPush: (data: object) => void;
    /** The diagram the page opens on, to make a newer revision of. */
    canvasSample: object;
  }
}

/** A host that keeps what it is sent: each edit applied, each image kept by its digest. */
function keeping(): CanvasHost {
  const images = new Map<string, Blob>();
  let version = 1;
  window.canvasSent = { commits: [], uploads: [], said: [] };
  return {
    async commit(_, edit) {
      window.canvasSent.commits.push(edit);
      version = edit.baseVersion + 1;
      return { outcome: "applied", version };
    },
    head: async () => null,
    async upload(_, image) {
      const digest = [
        ...new Uint8Array(await crypto.subtle.digest("SHA-256", await image.arrayBuffer())),
      ]
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("");
      images.set(digest, image);
      window.canvasSent.uploads.push(image.type);
      return {
        outcome: "done",
        result: { sha256: digest, size: image.size, media_type: image.type },
      };
    },
    read: async (_, sha256) => images.get(sha256) ?? null,
    mayEdit: async () => true,
    presence: (_, heard) => {
      window.canvasHeard = heard;
      return { say: (said) => window.canvasSent.said.push(said), close: () => undefined };
    },
  };
}

/** A diagram the test may edit, through a host of the page's own, and push newer revisions of. */
function Editable() {
  const [host] = useState(keeping);
  const [shown, setShown] = useState({ data: SAMPLE as object, version: 1 });
  window.canvasSample = SAMPLE;
  window.canvasPush = (data) => setShown((now) => ({ data, version: now.version + 1 }));
  return (
    <ShownContext value={{ id: "d1", version: shown.version }}>
      <CanvasHostContext value={host}>{diagram.render(shown.data as never)}</CanvasHostContext>
    </ShownContext>
  );
}

const drawing = asked.get("diagram");
if (drawing !== null) {
  // A diagram as the diagrams worker draws one from Mermaid, its first label holding markup; or
  // one written by a hostile hand; or one that can't be drawn as given.
  const card = diagram.render((DIAGRAMS[drawing] ?? SAMPLE) as never);
  flushSync(() => root.render(drawing === "edit" ? <Editable /> : card));
}
