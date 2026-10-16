import { describe, expect, test } from "vitest";
import { allows, elect, ids, offersChoice, parse } from "./spdx";

const allowed = new Set(["mit", "isc", "apache-2.0", "bsd-3-clause"]);
/** The expression a text spells, for a test that means it to be valid. */
function expressionOf(text: string) {
  const expression = parse(text);
  if (expression === undefined) {
    throw new Error(`${text} isn't an expression`);
  }
  return expression;
}

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
    // Read as MIT OR (GPL-3.0-only AND ISC): the MIT side alone allows it.
    expect(ok("MIT OR GPL-3.0-only AND ISC")).toBe(true);
    // Read as (GPL-3.0-only AND ISC) OR GPL-2.0-only: neither side is allowed.
    expect(ok("GPL-3.0-only AND ISC OR GPL-2.0-only")).toBe(false);
  });

  test("an OR is elected to its first allowed alternative", () => {
    const elected = (text: string) => {
      const expression = parse(text);
      return expression === undefined ? undefined : elect(expression, allowed);
    };
    expect(elected("MIT OR GPL-3.0-only")).toEqual(["MIT"]);
    expect(elected("GPL-3.0-only OR ISC")).toEqual(["ISC"]);
    expect(elected("(GPL-3.0-only OR MIT) AND Apache-2.0")).toEqual(["MIT", "Apache-2.0"]);
    expect(elected("MIT AND ISC")).toEqual(["MIT", "ISC"]);
    expect(elected("MIT AND GPL-3.0-only")).toBeUndefined();
    expect(elected("GPL-2.0-only OR GPL-3.0-only")).toBeUndefined();
  });

  test("the identifiers, and whether there is a choice", () => {
    const expression = parse("(MIT OR Apache-2.0) AND GPL-2.0+");
    expect(expression && ids(expression)).toEqual(["MIT", "Apache-2.0", "GPL-2.0"]);
    expect(expression && offersChoice(expression)).toBe(true);
    expect(offersChoice(expressionOf("MIT AND ISC"))).toBe(false);
  });
});
