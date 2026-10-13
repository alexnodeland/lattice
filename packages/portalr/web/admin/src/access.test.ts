import { expect, test } from "vitest";
import { ACCESS, anyPart, byKind, fromKey, keyOf, PARTS, where, who, whom } from "./access";

test("each part of Access reads with an action Access asks about", () => {
  for (const { reads } of PARTS) {
    expect(ACCESS).toContain(reads);
  }
});

test("Access is on the rail where any of its parts may be read", () => {
  expect(anyPart(new Set())).toBe(false);
  expect(anyPart(new Set(["grantr:remove_member"]))).toBe(false);
  expect(anyPart(new Set(["grantr:issue_key"]))).toBe(true);
});

test("a member is named with their kind, and people are listed first", () => {
  const ci = { kind: "service_principal", id: "ci" } as const;
  const bob = { kind: "user", id: "bob" } as const;
  const amy = { kind: "user", id: "amy" } as const;
  expect(who(ci)).toBe("ci (service principal)");
  expect(who(bob)).toBe("bob (person)");
  expect([ci, bob, amy].sort(byKind)).toEqual([amy, bob, ci]);
});

test("a grant reads as whom it is to, and where", () => {
  expect(whom({ kind: "group", id: "ops" })).toBe("ops (group)");
  expect(whom({ kind: "rule", rule: "tickets:triage", workspace: "ws_1" })).toBe(
    "tickets:triage (rule in ws_1)",
  );
  expect(whom({ kind: "user", id: "bob" })).toBe("bob (person)");
  expect(where({ kind: "tenant" })).toBe("the tenant");
  expect(where({ kind: "workspace", workspace: "ws_1" })).toBe("workspace ws_1");
  expect(where({ kind: "thread", workspace: "ws_1", id: "t_1" })).toBe("thread t_1 in ws_1");
});

test("a form's kind:id names a grantee of the kinds it takes, and nothing else", () => {
  const kinds = ["user", "group"] as const;
  expect(fromKey(keyOf({ kind: "group", id: "ops" }), kinds)).toEqual({ kind: "group", id: "ops" });
  expect(fromKey("user:a:b", kinds)).toEqual({ kind: "user", id: "a:b" });
  for (const key of ["ops", "service_principal:ci", "user:", "rule:x"]) {
    expect(fromKey(key, kinds)).toBeNull();
  }
});
