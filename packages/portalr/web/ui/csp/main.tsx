/**
 * The page the CSP tests drive: ui's Markdown and a dashboard, built as app and admin are, and
 * served with the Content-Security-Policy both UIs share (`policy.txt`), so whatever it renders
 * meets it. What it draws its address names, from the page's own tasks, as the UIs draw (portalr
 * ADR-0047): `?markdown=` the Markdown given, whole, or with `&stream` a character at a time, as an
 * agent's run writes it, with the integrations `&on=` and `&off=` name, such as `markdown:math`,
 * switched so and the rest their defaults, and on the root `data-drawn` once it is whole, or
 * `data-error` if it stopped; `?dashboard` the dashboard gallery; `?eval` an evaluated string; and
 * `?app=` a mini app of that HTML, run in the sandbox at `&apps=` (portalr ADR-0051); and `?diagram`
 * the app's card of a diagram, whose canvas the test opens (portalr ADR-0072).
 */

import type { IntegrationKey } from "@portalr/client";
import "../src/styles.css";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";
// The app's diagram card and its canvas add-on, built as app's build builds them (portalr ADR-0072).
import { diagram } from "../../app/src/diagram";
import { AppHostContext, DashboardView, IntegrationsContext, Markdown } from "../src";
import { AppFrame } from "../src/app-frame";
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
if (asked.has("diagram")) {
  // A diagram as the diagrams worker draws one from Mermaid, its first label holding markup.
  flushSync(() => root.render(diagram.render(SAMPLE)));
}
