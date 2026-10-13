import { expect, test } from "vitest";
import { ACCESS, anyPart, byKind, PARTS, who } from "./access";

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
