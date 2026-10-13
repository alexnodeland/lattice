import { expect, test } from "vitest";
import { ACCESS, anyPart, PARTS } from "./access";

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
