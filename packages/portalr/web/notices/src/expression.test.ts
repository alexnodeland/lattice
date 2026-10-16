import { expect, test } from "vitest";
import { bundledLicences, expressionProblems } from "./expression";
import type { Entry } from "./render";

const entry = (licence: string, usedUnder?: string): Entry => ({
  name: "p",
  version: "1.0.0",
  licence,
  usedUnder,
  hasText: true,
});

test("the licences bundled are those declared, and by an OR the one it is used under", () => {
  const found = bundledLicences([
    entry("MIT"),
    entry("MIT AND ISC"),
    entry("(GPL-3.0-only OR Apache-2.0)", "Apache-2.0"),
    entry("(MIT OR BSD-3-Clause)"),
  ]);
  expect(found).toEqual(["Apache-2.0", "BSD-3-Clause", "ISC", "MIT"]);
});

test("a licence that names no identifier can't be stated", () => {
  expect(() => bundledLicences([entry("SEE LICENSE IN LICENSE")])).toThrow("names no identifier");
});

test("the expression lists what is bundled and the wheel's own, no more and no less", () => {
  const expression = "MIT AND OFL-1.1 AND Apache-2.0 AND ISC";
  expect(expressionProblems(expression, ["ISC", "MIT"])).toEqual([]);
  expect(expressionProblems(expression, ["ISC", "MIT", "0BSD"])).toEqual([
    "the license expression lacks 0BSD, which is bundled",
  ]);
  expect(expressionProblems(expression, ["MIT"])).toEqual([
    "the license expression lists ISC, which nothing bundled is under",
  ]);
  expect(expressionProblems("not spdx at all(", [])).toEqual([
    "the license expression, not spdx at all(, isn't SPDX",
  ]);
});
