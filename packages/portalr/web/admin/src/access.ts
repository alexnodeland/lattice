/**
 * What the Access area asks grantr, on the tenant: each of its parts reads with the action its
 * changes take, so a part shows only where its read is allowed, and Access only where one is.
 */

import { allowedIn, type createQueries } from "@portalr/client";

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
export const accessIn = (queries: ReturnType<typeof createQueries>, tenant: string) =>
  allowedIn(queries, tenant, { kind: "tenant" }, ACCESS);

/** Whether any part of Access may be read: whether Access joins the rail. */
export const anyPart = (allowed: ReadonlySet<string>) =>
  PARTS.some(({ reads }) => allowed.has(reads));
