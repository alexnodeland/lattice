/**
 * Product analytics in the app (lattice RFC-0008): the person's answer, in the account menu, and
 * the pages they open, sent only with their yes.
 *
 * Where the deployment has no analytics, there is no switch and nothing is sent. The capture
 * code is fetched only once the person has said yes: someone who never does never loads it.
 * A page is named by the router's own name for its route, never the address in the bar.
 */

import {
  type Api,
  answerConsent,
  type Consent,
  carryAnalyticsSession,
  NOT_READ,
  readConsent,
} from "@portalr/client";
import type { AnalyticsAnswer } from "@portalr/ui";
import { Account, loadCapture } from "@portalr/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouteContext, useRouterState } from "@tanstack/react-router";
import { useEffect, useState } from "react";

const consentKey = (user: string) => ["portalr", "analytics", "consent", user] as const;

/**
 * The privacy guide, which says what is shared and how it is kept. lattice's public docs: a
 * deployment's own guide, from its kit or config, is a follow-up (lattice RFC-0008).
 */
const PRIVACY_GUIDE = "https://lattice.alexnodeland.com/portalr/guides/privacy/#product-analytics";

/** How often an answer whose deletion isn't done yet is read again, until it is, in ms. */
const UNTIL_DELETED = 30_000;

/**
 * The person's answer, read once and shared by every screen that shows or uses it. A read that
 * fails keeps the last answer read, or `NOT_READ` (not sharing) before the first. Only the account
 * menu reads it again while a deletion is owed (`poll`): one reader, not one per screen.
 */
function useAnswer(poll = false) {
  const { config, api, user } = useRouteContext({ from: "/_signed" });
  const enabled = config.readers.analytics === true;
  const { data = NOT_READ } = useQuery({
    queryKey: consentKey(user),
    queryFn: () => readConsent(api),
    enabled,
    staleTime: Number.POSITIVE_INFINITY,
    // Read again while a deletion is owed, so the note goes when the relay has done it.
    refetchInterval: (query) => (poll && query.state.data?.deleting ? UNTIL_DELETED : false),
  });
  return { enabled, consent: data, api, user };
}

/** Whether the person has said yes, where the deployment has analytics. */
export function useGiven(): boolean {
  const { enabled, consent } = useAnswer();
  return enabled && consent.given;
}

/** The person's answer, for the account menu, where the deployment has analytics; else none. */
function useConsent(): AnalyticsAnswer | undefined {
  const { enabled, consent, api, user } = useAnswer(true);
  const client = useQueryClient();
  const key = consentKey(user);
  const { mutate, isError } = useMutation({
    mutationFn: (answer: boolean) => answerConsent(api, answer),
    onMutate: async (answer: boolean) => {
      await client.cancelQueries({ queryKey: key });
      const before = client.getQueryData<Consent>(key);
      // A deletion owed stays owed whatever the answer: the relay says when it is done.
      client.setQueryData<Consent>(key, { given: answer, deleting: before?.deleting ?? false });
      return { before };
    },
    // Not recorded: the switch goes back to the answer the relay has, and the status says so.
    onError: (_error, _answer, context) => client.setQueryData(key, context?.before),
    onSettled: () => client.invalidateQueries({ queryKey: key }),
  });
  return enabled
    ? {
        given: consent.given,
        onAnswer: mutate,
        deleting: consent.deleting,
        failed: isError,
        guide: PRIVACY_GUIDE,
      }
    : undefined;
}

/** The account menu, with the person's answer to analytics where the deployment has it. */
export function AppAccount() {
  const { signed } = useRouteContext({ from: "/_signed" });
  return <Account signed={signed} analytics={useConsent()} />;
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
