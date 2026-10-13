/**
 * What the Access area asks grantr, on the tenant: each of its parts reads with the action its
 * changes take, so a part shows only where its read is allowed, and Access only where one is.
 */

import { allowedIn, changedAccess, type createQueries, type GrantrApi } from "@portalr/client";
import { useSuspenseQuery } from "@tanstack/react-query";
import { getRouteApi, notFound } from "@tanstack/react-router";
import { useCallback, useMemo } from "react";
import type { Context } from "./context";

type Member = GrantrApi.components["schemas"]["Member"];

/** Every action Access's screens ask about, once per screen. */
export const ACCESS = [
  "grantr:add_member",
  "grantr:remove_member",
  "grantr:manage_groups",
  "grantr:issue_key",
  "grantr:revoke_key",
] as const;

/** Each part of Access, and the action its read takes. */
export const PARTS = [
  { part: "members", label: "Members", reads: "grantr:add_member" },
  { part: "groups", label: "Groups", reads: "grantr:manage_groups" },
  { part: "keys", label: "Keys", reads: "grantr:issue_key" },
] as const;

/** The one read of grantr's checks a screen of Access makes. */
const accessIn = (queries: ReturnType<typeof createQueries>, tenant: string) =>
  allowedIn(queries, tenant, { kind: "tenant" }, ACCESS);

/** What grantr allows in the tenant, from the checks' cache where they are there. */
export async function allowedNow(
  { queries, queryClient }: Pick<Context, "queries" | "queryClient">,
  tenant: string,
): Promise<ReadonlySet<string>> {
  const checks = accessIn(queries, tenant);
  return checks.select(await queryClient.ensureQueryData(checks));
}

/** A part's gate, before it loads: a part whose read grantr doesn't allow is not found. */
export async function opening(
  context: Pick<Context, "queries" | "queryClient">,
  tenant: string,
  reads: (typeof ACCESS)[number],
): Promise<void> {
  if (!(await allowedNow(context, tenant)).has(reads)) {
    throw notFound();
  }
}

/** Whether any part of Access may be read: whether Access joins the rail. */
export const anyPart = (allowed: ReadonlySet<string>) =>
  PARTS.some(({ reads }) => allowed.has(reads));

/** A member's kind, as people read it. */
export const KIND: Record<Member["kind"], string> = {
  user: "person",
  service_principal: "service principal",
};

/** A member as people read it: its id, and its kind beside it, such as "ci (service principal)". */
export const who = (member: Member) => `${member.id} (${KIND[member.kind]})`;

/** Members in the order Access lists them: people first, then service principals, each by id. */
export const byKind = (a: Member, b: Member) =>
  Number(a.kind !== "user") - Number(b.kind !== "user") || a.id.localeCompare(b.id);

const tenantRoute = getRouteApi("/_signed/t/$tenant");

/**
 * What a screen of Access needs of grantr: what it allows in the tenant, read live, so a change
 * shows at once, and `changed`, which reads grantr's answers again after a change, done or not.
 */
export function useAccess(tenant: string) {
  const { queries, queryClient } = tenantRoute.useRouteContext();
  const checks = useMemo(() => accessIn(queries, tenant), [queries, tenant]);
  const { data: allowed } = useSuspenseQuery(checks);
  const changed = useCallback(
    <A>(answer: Promise<A>) => changedAccess(queryClient, tenant, answer),
    [queryClient, tenant],
  );
  return { allowed, changed };
}
