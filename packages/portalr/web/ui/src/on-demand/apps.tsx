/**
 * A mini app running (portalr ADR-0051), loaded with the first app a page runs: its frame, the
 * sandbox on the apps' origin, and the bridge that answers it as the person viewing it, with the
 * host's colours and modes, its state coalesced to one version every five seconds, and the dialog
 * of the host's own, outside the frame, in which a submission or a link is confirmed. `AppFrame`
 * draws the chrome round it, and decides whether it runs.
 */

import { AlertDialog } from "@base-ui/react/alert-dialog";
import { useEffect, useRef, useState } from "react";
import { Alert } from "../alert";
import {
  Bridge,
  CALLS_A_MINUTE,
  type JsonObject,
  type Question,
  StateKeeper,
  type Written,
} from "../app-bridge";
import type { AppHost, ReadApp } from "../app-frame";
import type { Shown } from "../artifacts";
import { Button } from "../button";
import { actions, backdrop, description, title as heading, popup } from "../dialog";
import { offSaid } from "../integrations";
import { isObject } from "../json";
import type { Sent } from "../sending";
import { submissionId } from "../submission-id";

/** The height a frame starts at, in pixels, until its app asks for another. */
const FIRST_HEIGHT = 360;

/**
 * The host's colours an app is given, by portalr's names and MCP Apps', resolved to what the
 * browser draws: the app's frame is another document, which reads none of the host's properties.
 */
const COLOURS: readonly (readonly [string, string | null])[] = [
  ["paper", "--color-background-primary"],
  ["surface", "--color-background-secondary"],
  ["wash", "--color-background-tertiary"],
  ["fg", "--color-text-primary"],
  ["muted", "--color-text-secondary"],
  ["danger", "--color-text-danger"],
  ["line", "--color-border-primary"],
  ["edge", "--color-border-secondary"],
  ["focus", "--color-ring-primary"],
  ["accent", null],
  ["on-accent", null],
  ["chart-1", null],
  ["chart-2", null],
  ["chart-3", null],
];

/** What changes the host's context: the scheme and colour-blind mode, on any element. */
const ATTRIBUTES = ["data-theme", "data-cvd"];
const MEDIA = [
  "(prefers-color-scheme: dark)",
  "(forced-colors: active)",
  "(prefers-reduced-motion: reduce)",
];

/** The host's context as MCP Apps' `hostContext` has it, with the modes portalr has besides. */
function hostContext(within: Element): JsonObject {
  const probe = document.createElement("span");
  within.append(probe);
  const variables: Record<string, string> = {};
  for (const [name, theirs] of COLOURS) {
    probe.style.color = `var(--${name})`;
    const colour = getComputedStyle(probe).color;
    variables[`--${name}`] = colour;
    if (theirs !== null) {
      variables[theirs] = colour;
    }
  }
  probe.remove();
  const chosen = within.closest("[data-theme]")?.getAttribute("data-theme");
  const dark =
    chosen === "dark" || (chosen !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  return {
    theme: dark ? "dark" : "light",
    styles: { variables },
    displayMode: "inline",
    availableDisplayModes: ["inline"],
    locale: navigator.language,
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    platform: "web",
    colourBlind: within.closest("[data-cvd]") !== null,
    forcedColours: matchMedia("(forced-colors: active)").matches,
    reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
  };
}

/** A question open, and how its answer, yes or no, reaches the bridge. */
type Asking = Question & { readonly settle: (yes: boolean) => void };

/** Why an app's state wasn't saved, said of the workspace or the viewer, never of the app. */
function unsaved(rejection: unknown): string {
  if (isObject(rejection) && rejection.type === "not_enabled") {
    return `${offSaid("ui:mini-apps")} What you did in the app isn't saved.`;
  }
  if (isObject(rejection) && rejection.type === "forbidden") {
    return "You can't change this app, so what you do in it isn't saved.";
  }
  return "What you did in the app couldn't be saved.";
}

/** How a write of the state ended, as the bridge's state keeper reads it. */
async function written(sent: Sent): Promise<Written> {
  const settled = await sent;
  if (settled.outcome === "done") {
    return "done";
  }
  const rejection = settled.result?.rejection;
  return isObject(rejection) && rejection.type === "version_conflict"
    ? "stale"
    : { refused: rejection ?? settled.outcome };
}

/** The app running: its frame, the bridge's answers, and what the person is asked. */
export function Running({
  app,
  shown,
  host,
  origin,
  after,
}: {
  app: ReadApp;
  shown: Shown;
  host: AppHost;
  origin: string;
  after: string;
}) {
  // The frame itself, so the bridge starts again with a new one, as when the HTML changes.
  const [element, setElement] = useState<HTMLIFrameElement | null>(null);
  const [height, setHeight] = useState(FIRST_HEIGHT);
  const [failure, setFailure] = useState<string | null>(null);
  const [asking, setAsking] = useState<Asking | null>(null);
  // The question open, read at once by the bridge, which a state would give a render late.
  const open = useRef<Asking | null>(null);
  const [quieted, setQuieted] = useState(false);
  const [run, setRun] = useState({ html: app.html, count: 0 });
  // A new version's HTML runs afresh; its state alone changing does not.
  if (run.html !== app.html) {
    setRun({ html: app.html, count: run.count + 1 });
  }
  const keeper = useRef<StateKeeper | null>(null);
  const head = useRef({ app, shown });
  head.current = { app, shown };

  useEffect(() => {
    keeper.current?.rebase({ state: app.state, version: shown.version });
  }, [app.state, shown.version]);

  useEffect(() => {
    if (element === null) {
      return;
    }
    const { id } = head.current.shown;
    const kept = new StateKeeper(
      { state: head.current.app.state, version: head.current.shown.version },
      (state, version) => written(host.setState(id, version, state)),
      (rejection) => setFailure(unsaved(rejection)),
    );
    keeper.current = kept;
    const bridge = new Bridge({
      source: element.contentWindow,
      origin,
      post: (message) => element.contentWindow?.postMessage(message, origin),
      state: kept,
      host: {
        app: () => ({ title: head.current.app.title, html: head.current.app.html }),
        context: () => hostContext(element),
        ask: (question) =>
          new Promise<boolean>((settle) => {
            if (open.current !== null) {
              settle(false); // one question at a time: a second is declined
              return;
            }
            open.current = { ...question, settle };
            setAsking(open.current);
          }),
        submit: async (values) => {
          const nonce = crypto.randomUUID();
          const { id: appId, version } = head.current.shown;
          const submission = await submissionId(appId, { submissions: "many", nonce });
          const sent = await host.submit(submission, { app_id: appId, version, values, nonce });
          return sent.outcome === "done" ? submission : null;
        },
        open: (url) => window.open(url, "_blank", "noopener,noreferrer"),
        resize: setHeight,
        quieted: () => setQuieted(true),
      },
    });
    const heard = (event: MessageEvent) => bridge.heard(event);
    addEventListener("message", heard);

    // The host's colours and modes, sent again whenever they change.
    const changed = () => bridge.contextChanged();
    const observer = new MutationObserver(changed);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ATTRIBUTES,
      subtree: true,
    });
    const media = MEDIA.map((query) => matchMedia(query));
    for (const each of media) {
      each.addEventListener("change", changed);
    }
    return () => {
      removeEventListener("message", heard);
      observer.disconnect();
      for (const each of media) {
        each.removeEventListener("change", changed);
      }
      kept.stop();
      keeper.current = null;
      open.current?.settle(false);
      open.current = null;
    };
  }, [element, host, origin]);

  const settle = (yes: boolean) => {
    open.current?.settle(yes);
    open.current = null;
    setAsking(null);
  };
  return (
    <>
      <a
        href={`#${CSS.escape(after)}`}
        className="sr-only text-accent underline focus-visible:not-sr-only focus-visible:outline-2 focus-visible:outline-focus"
      >
        Skip past {app.title}
      </a>
      <div className="overflow-hidden rounded-lg border-2 border-edge bg-paper forced-colors:border-[CanvasText]">
        <iframe
          key={run.count}
          ref={setElement}
          title={`${app.title}: an app made by the agent`}
          src={`${origin}/?host=${encodeURIComponent(location.origin)}`}
          sandbox="allow-scripts allow-same-origin"
          referrerPolicy="no-referrer"
          className="block w-full"
          style={{ height }}
        />
      </div>
      <p id={after} tabIndex={-1} className="sr-only">
        End of {app.title}.
      </p>
      {quieted && (
        <Alert tone="warn">
          This app sent more than {CALLS_A_MINUTE} messages in a minute, so it isn't answered for
          now.
        </Alert>
      )}
      {failure && <Alert tone="warn">{failure}</Alert>}
      <AlertDialog.Root open={asking !== null} onOpenChange={(open) => open || settle(false)}>
        <AlertDialog.Portal>
          <AlertDialog.Backdrop className={backdrop} />
          <AlertDialog.Popup className={popup}>
            {asking?.kind === "submit" && (
              <>
                <AlertDialog.Title className={heading}>
                  Send this from {app.title}?
                </AlertDialog.Title>
                <AlertDialog.Description className={description}>
                  The app made by the agent asks to send this, as you, to this thread.
                </AlertDialog.Description>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-md bg-wash p-3 font-mono text-fg text-xs">
                  {JSON.stringify(asking.values, null, 2)}
                </pre>
              </>
            )}
            {asking?.kind === "link" && (
              <>
                <AlertDialog.Title className={heading}>Open this link?</AlertDialog.Title>
                <AlertDialog.Description className={description}>
                  The app made by the agent asks to open it in a new tab.
                </AlertDialog.Description>
                <p className="break-all font-mono text-fg text-sm">{asking.url}</p>
              </>
            )}
            <div className={actions}>
              <AlertDialog.Close render={<Button variant="secondary" />}>
                {asking?.kind === "link" ? "Don't open it" : "Don't send it"}
              </AlertDialog.Close>
              <Button onClick={() => settle(true)}>
                {asking?.kind === "link" ? "Open the link" : "Send it"}
              </Button>
            </div>
          </AlertDialog.Popup>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </>
  );
}
