/**
 * grantr's audit log as people read it: who made each change, and what it was, in a sentence,
 * for each type of event grantr records (portalr ADR-0026).
 */

import { type AuditFilter, type GrantrApi, type Names, shortId } from "@portalr/client";
import { type Named, peopleIn, possessive, where, who, whom } from "./access";

type Subject = GrantrApi.components["schemas"]["Subject"];
type AuditEvent = GrantrApi.components["schemas"]["AuditEvent"];
type AuditEntry = GrantrApi.components["schemas"]["AuditEntry"];
type AuditType = GrantrApi.components["schemas"]["AuditType"];

/** Who made a change: a member, a rule, the agent, or no one, for the first operator's grant. */
export function actor(by: Subject | null, names: Names = shortId): string {
  if (by === null) {
    return "no one";
  }
  return by.kind === "agent" ? "the agent" : whom(by, names);
}

/** The ids of the people an entry names: who made it, and whom it is about. */
export function peopleOf(entry: AuditEntry): string[] {
  const { by, event } = entry;
  const named: Named[] = by === null ? [] : [by];
  switch (event.type) {
    case "tenant_created":
    case "deployment_tenant_created":
      named.push({ kind: "user", id: event.owner });
      break;
    case "member_added":
    case "member_removed":
      named.push(event.member);
      break;
    case "group_defined":
      named.push(...event.members);
      break;
    case "granted":
    case "revoked":
      named.push(event.grant.to);
      break;
    case "tenant_deleted":
    case "group_deleted":
    case "role_defined":
    case "role_deleted":
    case "key_issued":
    case "key_revoked":
    case "restricted":
    case "unrestricted":
    case "integration_set":
    case "setting_set":
    case "binding_added":
    case "binding_removed":
    case "approval_asked":
    case "approval_answered":
    case "approval_closed":
    case "capability_called":
      break;
    default:
      // Every type is read above: a new type of grantr's fails to typecheck here.
      event satisfies never;
  }
  return peopleIn(named);
}

/** A list of names, or "no one" for none. */
const listed = (names: readonly string[]) => (names.length > 0 ? names.join(", ") : "no one");

/** What a change was, as a sentence's predicate: "added ci (service principal)". */
export function said(event: AuditEvent, names: Names = shortId): string {
  switch (event.type) {
    case "tenant_created":
      return `created the tenant, owned by ${who({ kind: "user", id: event.owner }, names)}`;
    case "deployment_tenant_created":
      return `created the tenant ${event.tenant}, owned by ${who({ kind: "user", id: event.owner }, names)}`;
    case "tenant_deleted":
      return "deleted the tenant";
    case "member_added":
      return `added ${who(event.member, names)}`;
    case "member_removed":
      return `removed ${who(event.member, names)}`;
    case "group_defined":
      return `set ${possessive(event.group)} members to ${listed(event.members.map((member) => who(member, names)))}`;
    case "group_deleted":
      return `deleted the group ${event.group}`;
    case "role_defined":
      return `set ${possessive(event.role.name)} actions to ${listed([...event.role.actions].sort())}`;
    case "role_deleted":
      return `deleted the role ${event.role}`;
    case "granted":
      return `granted ${event.grant.role} on ${where(event.grant.on)} to ${whom(event.grant.to, names)}`;
    case "revoked":
      return `revoked ${event.grant.role} on ${where(event.grant.on)} from ${whom(event.grant.to, names)}`;
    case "key_issued":
      return `issued the key ${event.key} to ${who(event.principal, names)}`;
    case "key_revoked":
      return `revoked the key ${event.key} of ${who(event.principal, names)}`;
    case "restricted":
      return `restricted ${where(event.on)}`;
    case "unrestricted":
      return `lifted the restriction on ${where(event.on)}`;
    case "integration_set": {
      const place = event.workspace === null ? "the tenant" : `workspace ${event.workspace}`;
      if (event.on !== null) {
        return `turned ${event.key} ${event.on ? "on" : "off"} in ${place}`;
      }
      // Unset, a workspace inherits the tenant's setting, and the tenant its default.
      return event.workspace === null
        ? `set ${event.key} back to the default in the tenant`
        : `set ${event.key} back to inherited in ${place}`;
    }
    case "setting_set": {
      const place = event.workspace === null ? "the tenant" : `workspace ${event.workspace}`;
      const value = (v: number | readonly string[]) => (typeof v === "number" ? `${v}` : listed(v));
      if (event.new === null) {
        return `unset ${event.key} in ${place}`;
      }
      const from = event.old === null ? "" : ` from ${value(event.old)}`;
      return `set ${event.key}${from} to ${value(event.new)} in ${place}`;
    }
    case "binding_added": {
      const what = event.types === null ? "" : ` (${listed(event.types)})`;
      const trust = event.trust === null ? "" : `, trusted as ${event.trust}`;
      return `bound ${event.source} ${event.connection}${what} to workspace ${event.workspace}${trust}`;
    }
    case "binding_removed":
      return `unbound ${event.source} ${event.connection} from workspace ${event.workspace}`;
    case "approval_asked":
      return `asked approval ${event.approval} to call ${event.capability} in workspace ${event.workspace}, as ${event.caller}`;
    case "approval_answered":
      return `${event.approved ? "approved" : "denied"} ${event.approval} on ${event.surface}`;
    case "approval_closed":
      return `closed ${event.approval}, ${event.state}: ${event.reason}`;
    case "capability_called": {
      const where = event.tenant
        ? `${event.tenant}'s workspace ${event.workspace}`
        : `workspace ${event.workspace}`;
      const through = event.client ? ` through ${event.client}` : "";
      return `called ${event.capability} in ${where}, as ${event.caller}${through}: ${event.outcome}`;
    }
    default: {
      // Every type is read above: a new type of grantr's fails to typecheck here.
      const unread: never = event;
      return unknown(unread);
    }
  }
}

/** An event of a type no case reads, named by its type alone. */
const unknown = (event: { readonly type: string }) =>
  `made a change of a kind admin doesn't know: ${event.type}`;

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
  integration_set: "Integrations switched",
  setting_set: "Settings narrowed",
  binding_added: "Sources bound",
  binding_removed: "Sources unbound",
  approval_asked: "Approvals asked",
  approval_answered: "Approvals answered",
  approval_closed: "Approvals closed",
  capability_called: "Capabilities called",
  tenant_created: "Tenant created",
  deployment_tenant_created: "Tenant created (deployment)",
  tenant_deleted: "Tenant deleted",
};

/** Each type of change, as the filter offers it, in LABELS' order: by what it changes. */
export const TYPES = Object.entries(LABELS).map(([value, label]) => ({ value, label }));

/** A type of change from the address, or undefined where it names none grantr has. */
const auditType = (value: unknown): AuditType | undefined =>
  Object.keys(LABELS).find((type): type is AuditType => type === value);

/** The kinds of subject the filter offers, as people read them. */
export const MAKERS = [
  { value: "", label: "Anyone" },
  { value: "user", label: "A person" },
  { value: "service_principal", label: "A service principal" },
  { value: "rule", label: "A rule" },
  { value: "agent", label: "The agent" },
] as const;

/** The kinds of maker grantr filters by: each the filter offers but anyone. */
const KINDS = MAKERS.flatMap((maker) => (maker.value === "" ? [] : [maker.value]));

/**
 * A value from the address, as text, trimmed: the router reads `?actor=42` as a number, and
 * `?actor=true` as a boolean, so those are text too; undefined for anything else, or nothing.
 */
function text(value: unknown): string | undefined {
  const read =
    typeof value === "string" || typeof value === "number" || typeof value === "boolean"
      ? String(value).trim()
      : "";
  return read === "" ? undefined : read;
}

/** What grantr takes as a person's or a service principal's id: no `:` or `~`, and no spaces. */
const ID = "[^:~\\s]+";
const PRINCIPAL_ID = new RegExp(`^${ID}$`);

/** The id field's pattern: an id, with spaces around it, which the filter trims. */
export const ID_FIELD = `\\s*${ID}\\s*`;

/**
 * The filter an address keeps, as grantr takes it: a type, and a subject only where its kind has
 * all it needs (an id but for the agent, and a workspace for a rule), as grantr refuses otherwise.
 */
export function filterOf(search: Record<string, unknown>): AuditFilter {
  const type = auditType(search.type);
  return { ...(type && { type }), ...makerOf(search) };
}

/**
 * The address's search as the route keeps it: each of the filter's keys, undefined where the
 * filter has none, so a key the address gave and grantr wouldn't take is put out of the search,
 * which the router otherwise keeps from the address.
 */
export const searchOf = (search: Record<string, unknown>): AuditFilter => ({
  type: undefined,
  actor_kind: undefined,
  actor: undefined,
  workspace: undefined,
  ...filterOf(search),
});

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
  return kind && actor && PRINCIPAL_ID.test(actor) ? { actor_kind: kind, actor } : {};
}
