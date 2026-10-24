/**
 * Product analytics in the app (lattice RFC-0008): the person's answer, in the account menu, and
 * the pages they open, sent only with their yes.
 *
 * Where the deployment has no analytics, there is no switch and nothing is sent. The capture
 * code is fetched only once the person has said yes: someone who never does never loads it.
 * A page is named by the router's own name for its route, never the address in the bar.
 */

import { type Api, answerConsent, carryAnalyticsSession, readConsent } from "@portalr/client";
import type { AnalyticsAnswer } from "@portalr/ui";
import { Account, loadCapture, NOT_SAVED } from "@portalr/ui";
import { useRouteContext, useRouterState } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useAnswering, useRead } from "./answers";

const consentKey = (user: string) => ["portalr", "analytics", "consent", user] as const;

/**
 * The privacy guide, which says what is shared and how it is kept. lattice's public docs: a
 * deployment's own guide, from its kit or config, is a follow-up (lattice RFC-0008).
 */
const PRIVACY_GUIDE = "https://lattice.alexnodeland.com/portalr/guides/privacy/#product-analytics";

/**
 * The person's answer, read once and shared by every screen that shows or uses it. A read that
 * fails keeps the last answer read, or `NOT_READ` (not sharing) before the first. Only the account
 * menu reads it again while a deletion is owed (`poll`): one reader, not one per screen.
 */
function useAnswer(poll = false) {
  const { config, api, user } = useRouteContext({ from: "/_signed" });
  const enabled = config.readers.analytics === true;
  const consent = useRead(api, consentKey(user), readConsent, enabled, poll);
  return { enabled, consent, api, user };
}

/** Whether the person has said yes, where the deployment has analytics. */
export function useGiven(): boolean {
  const { enabled, consent } = useAnswer();
  return enabled && consent.given;
}

/** The person's answer, for the account menu, where the deployment has analytics; else none. */
function useConsent(): AnalyticsAnswer | undefined {
  const { enabled, consent, api, user } = useAnswer(true);
  const { answer, failed } = useAnswering(api, consentKey(user), answerConsent, true, [
    // The relay withdraws replay with analytics' no: its answer is read again.
    ["portalr", "analytics", "replay", user],
  ]);
  return enabled
    ? {
        given: consent.given,
        onAnswer: answer,
        deleting: consent.deleting,
        failed,
        guide: PRIVACY_GUIDE,
      }
    : undefined;
}

/** Session replay's part of the app, fetched only where the deployment records replays. */
const loadReplay = () => import("./on-demand/replay-account");

/** Session replay's part, once it has loaded, where `wanted`: a chunk that won't load is none. */
export function useReplay(wanted: boolean) {
  const [loaded, setLoaded] = useState<Awaited<ReturnType<typeof loadReplay>> | null>(null);
  useEffect(() => {
    if (wanted) {
      loadReplay().then(setLoaded, () => undefined);
    }
  }, [wanted]);
  return loaded;
}

/**
 * The account menu, with the person's answer to analytics where the deployment has it, and beside
 * it to session replay where it records replays (portalr ADR-0077).
 */
export function AppAccount() {
  const { signed, config, api, user } = useRouteContext({ from: "/_signed" });
  const analytics = useConsent();
  const replay = useReplay(config.replay === true && analytics !== undefined);
  return replay && analytics ? (
    <replay.ReplayAccount api={api} user={user} analytics={analytics.given} notSaved={NOT_SAVED}>
      {(answer) => <Account signed={signed} analytics={{ ...analytics, replay: answer }} />}
    </replay.ReplayAccount>
  ) : (
    <Account signed={signed} analytics={analytics} />
  );
}

/** The router's name for the route a page is on: `/t/$tenant/w/$workspace/runs`, not its address. */
export const routeOf = (fullPath: string): string => fullPath.replace(/\/$/, "") || "/";

type Capture = InstanceType<Awaited<ReturnType<typeof loadCapture>>["Capture"]>;

/**
 * Each page the person opens in the tenant, sent with their yes: the capture code is fetched
 * then, and not before. A no, or leaving the tenant, closes it: what waits is dropped.
 */
export function usePageViews(api: Api, tenant: string, given: boolean) {
  const [capture, setCapture] = useState<Capture | null>(null);
  const fullPath = useRouterState({ select: (state) => state.matches.at(-1)?.fullPath ?? "/" });
  useEffect(() => {
    if (!given) {
      return;
    }
    let live = true;
    let opened: Capture | null = null;
    loadCapture()
      .then(({ Capture }) => {
        if (live) {
          opened = new Capture(api, tenant, carryAnalyticsSession);
          setCapture(opened);
        }
      })
      .catch(() => {
        // The chunk didn't load: nothing is sent, and the screen is as it was.
      });
    return () => {
      live = false;
      opened?.close();
      setCapture(null);
    };
  }, [api, tenant, given]);
  useEffect(() => {
    capture?.record({ event: "app.page.viewed.v1", route: routeOf(fullPath) });
  }, [capture, fullPath]);
}
