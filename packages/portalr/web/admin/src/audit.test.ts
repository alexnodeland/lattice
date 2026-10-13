import { expect, test } from "vitest";
import { actor, auditType, filterOf, said, TYPES } from "./audit";

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
    [{ type: "tenant_created", owner: "alice" }, "created the tenant, owned by alice"],
    [{ type: "tenant_deleted" }, "deleted the tenant"],
    [{ type: "member_added", member: ci }, "added ci (service principal)"],
    [{ type: "member_removed", member: bob }, "removed bob (person)"],
    [
      { type: "group_defined", group: "ops", members: [bob, ci] },
      "set ops's members to bob (person), ci (service principal)",
    ],
    [{ type: "group_defined", group: "ops", members: [] }, "set ops's members to no one"],
    [{ type: "group_deleted", group: "ops" }, "deleted the group ops"],
    [
      { type: "role_defined", role: { name: "triager", actions: ["b:y", "a:x"] } },
      "set triager's actions to a:x, b:y",
    ],
    [{ type: "role_deleted", role: "triager" }, "deleted the role triager"],
    [{ type: "granted", grant }, "granted viewer on workspace notes to ops (group)"],
    [{ type: "revoked", grant }, "revoked viewer on workspace notes from ops (group)"],
    [{ type: "key_issued", key: "k_1", principal: ci }, "issued the key k_1 to ci"],
    [{ type: "key_revoked", key: "k_1", principal: ci }, "revoked ci's key k_1"],
    [
      { type: "restricted", on: { kind: "thread", workspace: "notes", id: "t_1" } },
      "restricted thread t_1 in notes",
    ],
    [
      { type: "unrestricted", on: { kind: "thread", workspace: "notes", id: "t_1" } },
      "lifted the restriction on thread t_1 in notes",
    ],
  ];
  for (const [event, sentence] of cases) {
    expect(said(event)).toBe(sentence);
  }
});

test("the filter offers every type, and reads one back from the address", () => {
  expect(TYPES).toHaveLength(14);
  expect(auditType("granted")).toBe("granted");
  expect(auditType("nonsense")).toBeUndefined();
  expect(auditType(undefined)).toBeUndefined();
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
