/**
 * What the Access area asks grantr, on the tenant: each of its parts reads with the action its
 * changes take, so a part shows only where its read is allowed, and Access only where one is.
 */

import {
  allowedIn,
  changedAccess,
  type createQueries,
  type GrantrApi,
  type Refusal,
} from "@portalr/client";
import { useSuspenseQuery } from "@tanstack/react-query";
import { getRouteApi, notFound } from "@tanstack/react-router";
import { useCallback, useMemo } from "react";
import type { Context } from "./context";

type Member = GrantrApi.components["schemas"]["Member"];
type Grantee = GrantrApi.components["schemas"]["Grantee"];
type Resource = GrantrApi.components["schemas"]["Resource"];

/**
 * Every action a tenant's screens in admin ask grantr about, on the tenant, in one read per
 * screen: Access's, and reading the audit log, which puts Audit on the rail.
 */
export const TENANT_ACTIONS = [
  "grantr:add_member",
  "grantr:remove_member",
  "grantr:manage_groups",
  "grantr:issue_key",
  "grantr:revoke_key",
  "grantr:define_role",
  "grantr:grant",
  "grantr:revoke",
  "grantr:delete_tenant",
  "grantr:read_audit",
] as const;

/** Each part of Access, and the action its read takes. */
export const PARTS = [
  { part: "members", label: "Members", reads: "grantr:add_member" },
  { part: "groups", label: "Groups", reads: "grantr:manage_groups" },
  { part: "keys", label: "Keys", reads: "grantr:issue_key" },
  { part: "roles", label: "Roles", reads: "grantr:define_role" },
  { part: "grants", label: "Grants", reads: "grantr:grant" },
] as const;

/** The one read of grantr's checks a screen of Access makes. */
const accessIn = (queries: ReturnType<typeof createQueries>, tenant: string) =>
  allowedIn(queries, tenant, { kind: "tenant" }, TENANT_ACTIONS);

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
  reads: (typeof TENANT_ACTIONS)[number],
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

/** Whom a grant is to, as people read it: a member as `who` names them, a group, or a rule. */
export function whom(grantee: Grantee): string {
  switch (grantee.kind) {
    case "group":
      return `${grantee.id} (group)`;
    case "rule":
      return `${grantee.rule} (rule in ${grantee.workspace})`;
    default:
      return who(grantee);
  }
}

/** Where a grant is, as people read it: "the tenant", "workspace ws_1", "thread t_1 in ws_1". */
export function where(on: Resource): string {
  if (on.kind === "tenant" || on.kind === "deployment") {
    return `the ${on.kind}`;
  }
  return on.kind === "workspace"
    ? `workspace ${on.workspace}`
    : `${on.kind} ${on.id} in ${on.workspace}`;
}

/** A member or a group as a form names it, `kind:id`, since grantr keeps the kinds apart. */
export const keyOf = (grantee: { readonly kind: string; readonly id: string }) =>
  `${grantee.kind}:${grantee.id}`;

/** A grantee from its `kind:id`, or null where it names none of `kinds`, or no id. */
export function fromKey<K extends "user" | "service_principal" | "group">(
  key: string,
  kinds: readonly K[],
): Keyed<K> | null {
  const at = key.indexOf(":");
  const kind = kinds.find((one) => one === key.slice(0, at));
  const id = key.slice(at + 1);
  return at < 0 || kind === undefined || id === "" ? null : keyed(kind, id);
}

/** A kind and an id, one kind at a time, so a union of kinds narrows as grantr's types do. */
type Keyed<K extends string> = K extends unknown ? { kind: K; id: string } : never;

const keyed = <K extends string>(kind: K, id: string) => ({ kind, id }) as Keyed<K>;

/** A name's possessive, as English writes it: "triager's", but "ops'" and "reviewers'". */
export const possessive = (name: string) => (/s$/i.test(name) ? `${name}'` : `${name}'s`);

/** What a form last said: done, or refused, and why. */
export type Said = { readonly said: string; readonly refused: boolean } | null;

/** A refusal of a form's own, before grantr is asked: no status, and why. */
export const refused = (reason: string): Refusal => ({
  outcome: "refused",
  status: 0,
  reasons: [reason],
});

/** "1 member", "2 members". */
export const counted = (count: number, noun: string) => `${count} ${noun}${count === 1 ? "" : "s"}`;

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
