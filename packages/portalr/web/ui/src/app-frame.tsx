/**
 * A mini app, run (lattice RFC-0005, portalr ADR-0051): the agent's HTML in the sandbox on the
 * apps' origin, inside chrome of the host's own that the app can't draw over. The chrome says it
 * is the agent's and runs sandboxed, apart from the person's session, and keeps its summary beside
 * it as its text equivalent. Nothing runs where the app is archived, where mini apps are off in the
 * workspace, where the deployment names no apps' origin, or where that origin is the portal's own;
 * the label and the summary are shown instead. The bridge answers the frame as the person viewing
 * it: its state, coalesced to one version every five seconds, and a submission, or a link, only
 * once they confirm it in a dialog of the host's, outside the frame.
 */

import { Bot } from "lucide-react";
import { createContext, use, useId } from "react";
import { Alert } from "./alert";
import type { JsonObject } from "./app-bridge";
import type { Submission } from "./artifactr-ui";
import type { Shown } from "./artifacts";
import { cn } from "./cn";
import { Icon } from "./icon";
import { IntegrationsContext, offSaid } from "./integrations";
import { useLoaded } from "./on-demand";
import type { Sent } from "./sending";
import { Reading } from "./skeleton";
import { TYPE } from "./type";

/** What a page lets its apps do, as the person viewing them. */
export interface AppHost {
  /** The origin apps run on, as `config.json` names it; null where the deployment runs none. */
  readonly origin: string | null;
  /** Write an app's state as the viewer: its `/state` replaced, on the version it was read at. */
  readonly setState: (id: string, version: number, state: JsonObject) => Sent;
  /** Create a submission to an app, with its derived id, as the viewer. */
  readonly submit: (id: string, submission: Submission) => Sent;
}

/** The page's app host, which a page that runs apps provides. */
export const AppHostContext = createContext<AppHost | null>(null);

/** An app as it is read: its title, its summary, its HTML and its state. */
export interface ReadApp {
  readonly title: string;
  readonly summary: string;
  readonly html: string;
  readonly state: JsonObject;
}

/** The integration that switches mini apps. */
export const MINI_APPS = "ui:mini-apps";

/** What the label says of every app, outside anything it draws. */
const LABEL = "Made by the agent. Runs sandboxed, apart from your session.";

/** What a preview tells its app that submits: nothing is sent from a preview. */
export const PREVIEW_SENDS_NOTHING = "This is a preview of a version: nothing is sent from it.";

/** The add-on that runs an app, loaded with the first app a page runs. */
const loadApps = () => import("./on-demand/apps");

/**
 * Why the app doesn't run here, or null where it does: archived, mini apps off, or no apps'
 * origin of its own.
 */
export function stillWhy(shown: Shown, off: boolean, host: AppHost | null): string | null {
  if (shown.archived) {
    return "This app is switched off: it was archived.";
  }
  if (off) {
    return offSaid(MINI_APPS);
  }
  if (!host?.origin || new URL(host.origin).origin === location.origin) {
    return "Apps don't run here: this deployment has no origin for them.";
  }
  return null;
}

/**
 * A mini app: run in its sandbox, as the person viewing it, or its label and summary alone. A
 * page that shows its title and summary itself, as a revision does, leaves them out (`titled`):
 * the host's label stays.
 */
export function AppFrame({
  app,
  shown,
  titled = true,
  preview = false,
}: {
  app: ReadApp;
  shown: Shown;
  titled?: boolean;
  /** A preview of a version, which writes no state and submits nothing (portalr ADR-0054). */
  preview?: boolean;
}) {
  const host = use(AppHostContext);
  const off = !use(IntegrationsContext)(MINI_APPS);
  const why = stillWhy(shown, off, host);
  const origin = why === null ? (host?.origin ?? null) : null;
  const { module: apps, failed } = useLoaded(loadApps, origin !== null);
  const named = useId();
  const after = useId();
  return (
    <section
      {...(titled ? { "aria-labelledby": named } : { "aria-label": app.title })}
      className="flex flex-col gap-3"
    >
      <div className="flex flex-col gap-1">
        {titled && (
          <h3 id={named} className={TYPE.label}>
            {app.title}
          </h3>
        )}
        <p className={cn(TYPE.note, "inline-flex items-center gap-1.5")}>
          <Icon icon={Bot} className="size-3.5 shrink-0" />
          {LABEL} Version {shown.version}.
        </p>
      </div>
      {titled && (
        <p className="whitespace-pre-wrap text-fg text-sm">{app.summary || "It has no summary."}</p>
      )}
      {origin === null || host === null ? (
        <Alert tone="info">{why}</Alert>
      ) : failed ? (
        <Alert tone="warn">This app couldn't be loaded. Reload the page to try again.</Alert>
      ) : apps === null ? (
        <Reading>Loading the app…</Reading>
      ) : (
        <apps.Running
          app={app}
          shown={shown}
          host={host}
          origin={origin}
          after={after}
          label={`${LABEL} Version ${shown.version}.`}
          {...(preview && { submitsNothing: PREVIEW_SENDS_NOTHING })}
        />
      )}
    </section>
  );
}
