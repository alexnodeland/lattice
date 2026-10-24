import { expect, test } from "vitest";
import cases from "../../../../artifactr/schemas/excalidraw_descriptions.json";
import { describe as described, MAX_DESCRIPTION, pyG } from "./diagram-text";

test.each(cases)("describes as artifactr does: $case", ({ name, elements, description }) => {
  expect(described(name, elements)).toBe(description);
});

test("the fixture holds what the port must agree on", () => {
  expect(cases.length).toBeGreaterThan(10);
  expect(cases.some((each) => [...each.description].length === MAX_DESCRIPTION)).toBe(true);
});

test("numbers are written as Python's g writes them, ties to even", () => {
  expect([1234565, 123456.5, 999999.5, -0, 0.1, 1e16, 2 ** -1074].map(pyG)).toEqual([
    "1.23456e+06",
    "123456",
    "1e+06",
    "-0",
    "0.1",
    "1e+16",
    "4.94066e-324",
  ]);
});

test("data of any shape is described, never thrown on", () => {
  for (const odd of [null, 3, "x", [], { a: null }, { a: [] }, { a: { type: 7, x: Number.NaN } }]) {
    expect(() => described("Odd", odd as never)).not.toThrow();
  }
});
