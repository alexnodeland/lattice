import { expect, test } from "vitest";
import { actor, filterOf, said, TYPES } from "./audit";

const ci = { kind: "service_principal", id: "ci" } as const;
const bob = { kind: "user", id: "bob" } as const;
const grant = {
  role: "viewer",
  on: { kind: "workspace", workspace: "notes" },
  to: { kind: "group", id: "ops" },
  tenant: "acme",
} as const;

test("who made a change: a member, a rule, the agent, or no one", () => {
  expect(actor(bob)).toBe("bob (person)");
  expect(actor({ kind: "rule", rule: "triage", workspace: "notes" })).toBe(
    "triage (rule in notes)",
  );
  expect(actor({ kind: "agent" })).toBe("the agent");
  expect(actor(null)).toBe("no one");
});

test("each type of change reads as a sentence", () => {
  const cases: [Parameters<typeof said>[0], string][] = [
    [{ type: "tenant_created", owner: "alice" }, "created the tenant, owned by alice (person)"],
    [
      { type: "deployment_tenant_created", tenant: "acme", owner: "alice" },
      "created the tenant acme, owned by alice (person)",
    ],
    [{ type: "tenant_deleted" }, "deleted the tenant"],
    [{ type: "member_added", member: ci }, "added ci (service principal)"],
    [{ type: "member_removed", member: bob }, "removed bob (person)"],
    [
      { type: "group_defined", group: "ops", members: [bob, ci] },
      "set ops' members to bob (person), ci (service principal)",
    ],
    [{ type: "group_defined", group: "ops", members: [] }, "set ops' members to no one"],
    [{ type: "group_deleted", group: "ops" }, "deleted the group ops"],
    [
      { type: "role_defined", role: { name: "triager", actions: ["b:y", "a:x"] } },
      "set triager's actions to a:x, b:y",
    ],
    [{ type: "role_deleted", role: "triager" }, "deleted the role triager"],
    [{ type: "granted", grant }, "granted viewer on workspace notes to ops (group)"],
    [{ type: "revoked", grant }, "revoked viewer on workspace notes from ops (group)"],
    [
      { type: "key_issued", key: "k_1", principal: ci },
      "issued the key k_1 to ci (service principal)",
    ],
    [
      { type: "key_revoked", key: "k_1", principal: ci },
      "revoked the key k_1 of ci (service principal)",
    ],
    [
      { type: "restricted", on: { kind: "thread", workspace: "notes", id: "t_1" } },
      "restricted thread t_1 in notes",
    ],
    [
      { type: "unrestricted", on: { kind: "thread", workspace: "notes", id: "t_1" } },
      "lifted the restriction on thread t_1 in notes",
    ],
    [
      { type: "integration_set", workspace: null, key: "excalidraw", on: false },
      "turned excalidraw off in the tenant",
    ],
    [
      { type: "integration_set", workspace: "notes", key: "ui:mini-apps", on: true },
      "turned ui:mini-apps on in workspace notes",
    ],
    [
      { type: "integration_set", workspace: "notes", key: "ui:mini-apps", on: null },
      "set ui:mini-apps back to inherited in workspace notes",
    ],
    [
      { type: "integration_set", workspace: null, key: "ui:mini-apps", on: null },
      "set ui:mini-apps back to the default in the tenant",
    ],
    [
      {
        type: "setting_set",
        workspace: "notes",
        key: "connect-per-hour:freecad",
        old: null,
        new: 10,
        version: 1,
      },
      "set connect-per-hour:freecad to 10 in workspace notes",
    ],
    [
      {
        type: "setting_set",
        workspace: null,
        key: "connect-per-hour:freecad",
        old: 20,
        new: 10,
        version: 2,
      },
      "set connect-per-hour:freecad from 20 to 10 in the tenant",
    ],
    [
      {
        type: "setting_set",
        workspace: null,
        key: "connect-per-hour:freecad",
        old: 10,
        new: null,
        version: 3,
      },
      "unset connect-per-hour:freecad in the tenant",
    ],
    [
      {
        type: "approval_asked",
        approval: "apr~acme~1",
        workspace: "notes",
        capability: "artifactr.edit_text",
        caller: "run:run_1",
      },
      "asked approval apr~acme~1 to call artifactr.edit_text in workspace notes, as run:run_1",
    ],
    [
      { type: "approval_answered", approval: "apr~acme~1", approved: true, surface: "portalr" },
      "approved apr~acme~1 on portalr",
    ],
    [
      { type: "approval_answered", approval: "apr~acme~1", approved: false, surface: "mcp" },
      "denied apr~acme~1 on mcp",
    ],
    [
      {
        type: "approval_closed",
        approval: "apr~acme~1",
        state: "expired",
        reason: "past its deadline unanswered",
      },
      "closed apr~acme~1, expired: past its deadline unanswered",
    ],
  ];
  for (const [event, sentence] of cases) {
    expect(said(event)).toBe(sentence);
  }
});

test("the filter offers every type, and reads one back from the address", () => {
  expect(TYPES).toHaveLength(20);
  expect(TYPES.find((type) => type.value === "tenant_created")?.label).toBe("Tenant created");
  expect(filterOf({ type: "granted" })).toEqual({ type: "granted" });
  expect(filterOf({ type: "nonsense" })).toEqual({});
});

test("the address keeps a filter grantr takes, and drops what grantr would refuse", () => {
  expect(filterOf({})).toEqual({});
  expect(filterOf({ type: "granted", actor_kind: "user", actor: "bob" })).toEqual({
    type: "granted",
    actor_kind: "user",
    actor: "bob",
  });
  expect(filterOf({ actor_kind: "rule", actor: "triage", workspace: "notes" })).toEqual({
    actor_kind: "rule",
    actor: "triage",
    workspace: "notes",
  });
  expect(filterOf({ actor_kind: "agent", actor: "ignored" })).toEqual({ actor_kind: "agent" });
  expect(filterOf({ actor_kind: "rule", actor: "triage" })).toEqual({});
  expect(filterOf({ actor_kind: "user" })).toEqual({});
  expect(filterOf({ type: "nonsense", actor_kind: "robot", actor: "x" })).toEqual({});
});

test("a number or a yes in the address is text, trimmed; an id grantr can't take is dropped", () => {
  expect(filterOf({ actor_kind: "user", actor: 42 })).toEqual({ actor_kind: "user", actor: "42" });
  expect(filterOf({ actor_kind: "service_principal", actor: " ci " })).toEqual({
    actor_kind: "service_principal",
    actor: "ci",
  });
  expect(filterOf({ actor_kind: "user", actor: true })).toEqual({
    actor_kind: "user",
    actor: "true",
  });
  expect(filterOf({ actor_kind: "service_principal", actor: "has:colon" })).toEqual({});
  expect(filterOf({ actor_kind: "user", actor: "a b" })).toEqual({});
  expect(filterOf({ actor_kind: "rule", actor: "tickets:triage", workspace: "notes" })).toEqual({
    actor_kind: "rule",
    actor: "tickets:triage",
    workspace: "notes",
  });
});
