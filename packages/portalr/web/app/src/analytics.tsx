/**
 * Product analytics in the app (lattice RFC-0008): the person's answer, in the account menu, and
 * the pages they open, sent only with their yes.
 *
 * Where the deployment has no analytics, there is no switch and nothing is sent. The capture
 * code is fetched only once the person has said yes: someone who never does never loads it.
 * A page is named by the router's own name for its route, never the address in the bar.
 */

import { type Api, answerConsent, readConsent } from "@portalr/client";
import type { AnalyticsAnswer } from "@portalr/ui";
import { Account, loadCapture } from "@portalr/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouteContext, useRouterState } from "@tanstack/react-router";
import { useEffect, useState } from "react";

const consentKey = (user: string) => ["portalr", "analytics", "consent", user] as const;

/** The privacy guide, which says what is shared and how it is kept. */
const PRIVACY_GUIDE = "https://lattice.alexnodeland.com/portalr/guides/privacy/#product-analytics";

/** The person's answer, for the account menu, where the deployment has analytics; else none. */
export function useConsent(): AnalyticsAnswer | undefined {
  const { config, api, user } = useRouteContext({ from: "/_signed" });
  const enabled = config.readers.analytics === true;
  const client = useQueryClient();
  const { data: given = false } = useQuery({
    queryKey: consentKey(user),
    queryFn: () => readConsent(api),
    enabled,
    staleTime: Number.POSITIVE_INFINITY,
  });
  const { mutate, data: answered } = useMutation({
    mutationFn: (answer: boolean) => answerConsent(api, answer),
    onMutate: (answer: boolean) => client.setQueryData(consentKey(user), answer),
    onSettled: () => client.invalidateQueries({ queryKey: consentKey(user) }),
  });
  // A no whose deletion ClickHouse didn't take yet: the relay tries it again, and says so here.
  const deleting = answered?.given === false && answered.deleted === false;
  return enabled ? { given, onAnswer: mutate, deleting, guide: PRIVACY_GUIDE } : undefined;
}

/** The account menu, with the person's answer to analytics where the deployment has it. */
export function AppAccount() {
  const { signed } = useRouteContext({ from: "/_signed" });
  return <Account signed={signed} analytics={useConsent()} />;
}

/** The router's name for the route a page is on: `/t/$tenant/w/$workspace/runs`, not its address. */
export const routeOf = (fullPath: string): string => fullPath.replace(/\/$/, "") || "/";

/**
 * Each page the person opens in the tenant, sent with their yes: the capture code is fetched
 * then, and not before.
 */
export function usePageViews(api: Api, tenant: string, given: boolean) {
  const [capture, setCapture] = useState<{ record: (route: string) => void } | null>(null);
  const fullPath = useRouterState({ select: (state) => state.matches.at(-1)?.fullPath ?? "/" });
  useEffect(() => {
    if (!given) {
      setCapture(null);
      return;
    }
    let live = true;
    void loadCapture().then(({ Capture }) => {
      if (!live) {
        return;
      }
      const sending = new Capture(api, tenant);
      setCapture({
        record: (route) => sending.record({ event: "app.page.viewed.v1", route }),
      });
    });
    return () => {
      live = false;
    };
  }, [api, tenant, given]);
  useEffect(() => {
    capture?.record(routeOf(fullPath));
  }, [capture, fullPath]);
}
