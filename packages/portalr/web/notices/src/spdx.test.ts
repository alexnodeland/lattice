import { describe, expect, test } from "vitest";
import { allows, parse } from "./spdx";

const allowed = new Set(["mit", "isc", "apache-2.0", "bsd-3-clause"]);
const ok = (text: string) => {
  const expression = parse(text);
  return expression !== undefined && allows(expression, allowed);
};

describe("SPDX expressions", () => {
  test.each([
    ["MIT", true],
    ["mit", true],
    ["MIT AND ISC", true],
    ["(MIT OR Apache-2.0)", true],
    ["MIT OR GPL-3.0-only", true],
    ["GPL-3.0-only OR MIT", true],
    ["MIT AND GPL-3.0-only", false],
    ["(GPL-3.0-only OR LGPL-3.0-only) AND MIT", false],
    ["(MIT AND (ISC OR GPL-2.0-only)) AND Apache-2.0", true],
    ["GPL-3.0-only", false],
    ["MIT+", true],
    ["Apache-2.0 WITH LLVM-exception", false],
  ])("%s is allowed: %s", (text, expected) => {
    expect(ok(text)).toBe(expected);
  });

  test.each([
    "",
    "SEE LICENSE IN LICENSE.md",
    "MIT AND",
    "(MIT",
    "MIT)",
    "MIT ISC",
    "AND MIT",
    "MIT WITH",
    "UNLICENSED, but ok",
    "MIT; ISC",
  ])("%j isn't an expression", (text) => {
    expect(parse(text)).toBeUndefined();
  });

  test("AND binds tighter than OR", () => {
    // MIT OR (GPL AND ISC): allowed by the MIT side alone.
    expect(ok("MIT OR GPL-3.0-only AND ISC")).toBe(true);
    // (MIT OR GPL) AND ISC would be allowed too; GPL AND ISC OR GPL is not.
    expect(ok("GPL-3.0-only AND ISC OR GPL-2.0-only")).toBe(false);
  });
});
