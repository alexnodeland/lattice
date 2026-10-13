/**
 * grantr's audit log as people read it: who made each change, and what it was, in a sentence,
 * for each type of event grantr records (portalr ADR-0026).
 */

import type { AuditFilter, GrantrApi } from "@portalr/client";
import { where, who, whom } from "./access";

type Subject = GrantrApi.components["schemas"]["Subject"];
type AuditEvent = GrantrApi.components["schemas"]["AuditEvent"];
type AuditType = GrantrApi.components["schemas"]["AuditType"];

/** Who made a change: a member, a rule, the agent, or no one, for the first operator's grant. */
export function actor(by: Subject | null): string {
  if (by === null) {
    return "no one";
  }
  return by.kind === "agent" ? "the agent" : whom(by);
}

/** A list of names, or "no one" for none. */
const listed = (names: readonly string[]) => (names.length > 0 ? names.join(", ") : "no one");

/** What a change was, as a sentence's predicate: "added ci (service principal)". */
export function said(event: AuditEvent): string {
  switch (event.type) {
    case "tenant_created":
      return `created the tenant, owned by ${event.owner}`;
    case "tenant_deleted":
      return "deleted the tenant";
    case "member_added":
      return `added ${who(event.member)}`;
    case "member_removed":
      return `removed ${who(event.member)}`;
    case "group_defined":
      return `set ${event.group}'s members to ${listed(event.members.map(who))}`;
    case "group_deleted":
      return `deleted the group ${event.group}`;
    case "role_defined":
      return `set ${event.role.name}'s actions to ${listed([...event.role.actions].sort())}`;
    case "role_deleted":
      return `deleted the role ${event.role}`;
    case "granted":
      return `granted ${event.grant.role} on ${where(event.grant.on)} to ${whom(event.grant.to)}`;
    case "revoked":
      return `revoked ${event.grant.role} on ${where(event.grant.on)} from ${whom(event.grant.to)}`;
    case "key_issued":
      return `issued the key ${event.key} to ${event.principal.id}`;
    case "key_revoked":
      return `revoked ${event.principal.id}'s key ${event.key}`;
    case "restricted":
      return `restricted ${where(event.on)}`;
    case "unrestricted":
      return `lifted the restriction on ${where(event.on)}`;
    default:
      return unknown(event);
  }
}

/** An event no case above reads: a new type of grantr's fails to typecheck here. */
function unknown(event: never): string {
  return `made a change of a kind admin doesn't know: ${JSON.stringify(event)}`;
}

/** Each type of change as the filter names it: a record, so a new type of grantr's must be named. */
const LABELS: Record<AuditType, string> = {
  member_added: "Members added",
  member_removed: "Members removed",
  group_defined: "Groups defined",
  group_deleted: "Groups deleted",
  role_defined: "Roles defined",
  role_deleted: "Roles deleted",
  granted: "Grants",
  revoked: "Revocations",
  key_issued: "Keys issued",
  key_revoked: "Keys revoked",
  restricted: "Restrictions",
  unrestricted: "Restrictions lifted",
  tenant_created: "The tenant created",
  tenant_deleted: "The tenant deleted",
};

/** Each type of change, as the filter offers it, grouped by what it changes. */
export const TYPES = Object.entries(LABELS).map(([value, label]) => ({ value, label }));

/** A type of change from the address, or undefined where it names none grantr has. */
export const auditType = (value: unknown): AuditType | undefined =>
  Object.keys(LABELS).find((type): type is AuditType => type === value);

/** The kinds of subject the filter offers, as people read them. */
export const MAKERS = [
  { value: "", label: "Anyone" },
  { value: "user", label: "A person" },
  { value: "service_principal", label: "A service principal" },
  { value: "rule", label: "A rule" },
  { value: "agent", label: "The agent" },
] as const;

const KINDS = ["user", "service_principal", "rule", "agent"] as const;

/** A string from the address, or undefined for anything else or nothing. */
const text = (value: unknown) => (typeof value === "string" && value !== "" ? value : undefined);

/**
 * The filter an address keeps, as grantr takes it: a type, and a subject only where its kind has
 * all it needs (an id but for the agent, and a workspace for a rule), as grantr refuses otherwise.
 */
export function filterOf(search: Record<string, unknown>): AuditFilter {
  const type = auditType(search.type);
  return { ...(type && { type }), ...makerOf(search) };
}

/** The subject an address names, where its kind has all it needs, or no one. */
function makerOf(search: Record<string, unknown>): AuditFilter {
  const kind = KINDS.find((one) => one === search.actor_kind);
  const actor = text(search.actor);
  const workspace = text(search.workspace);
  if (kind === "agent") {
    return { actor_kind: kind };
  }
  if (kind === "rule") {
    return actor && workspace ? { actor_kind: kind, actor, workspace } : {};
  }
  return kind && actor ? { actor_kind: kind, actor } : {};
}
