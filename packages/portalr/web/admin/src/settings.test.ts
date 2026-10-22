import { expect, test } from "vitest";
import { nameOf, numberOf, said, settersOf, settingRowsOf } from "./settings";

const RANGE = { type: "int_range", low: 0, high: 1000, universe: null } as const;

const state = (over: Partial<Parameters<typeof nameOf>[0]> = {}) => ({
  key: "connect-per-hour:freecad",
  description:
    "How many tries at code and network calls to a connected FreeCAD a workspace may make an hour.",
  kind: RANGE,
  default: 30,
  lowest: "workspace" as const,
  operator: 60,
  tenant: {
    value: 90,
    version: 3,
    by: { kind: "user" as const, id: "alice" },
    at: "2026-10-22T09:00:00Z",
    clamped: true,
  },
  workspace: null,
  version: 3,
  ceiling: 60,
  ceiling_set_by: "operator" as const,
  effective: 60,
  ...over,
});

test("a setting is named by what it limits, never by its key", () => {
  expect(nameOf(state())).toBe("FreeCAD's tries an hour");
  expect(nameOf(state({ description: "Days logs are kept." }))).toBe("Days logs are kept.");
});

test("a value is said as a number, or names, or none", () => {
  expect([said(5), said(["read", "run"]), said([])]).toEqual(["5", "read, run", "none"]);
});

test("a row says what applies, its ceiling and who set it, and whether it is clamped", () => {
  const [row] = settingRowsOf([state()], false, (id) => `${id}@acme.test`);
  expect(row).toMatchObject({
    name: "FreeCAD's tries an hour",
    effective: "60",
    ceiling: "At most 60: the operator's value.",
    clamped: true,
    version: 3,
    inherits: "the operator's",
  });
  const [unset] = settingRowsOf([state({ operator: null })], false, (id) => id);
  expect(unset?.inherits).toBe("the default");
  expect(row?.here?.value).toBe(90);
  const [inWorkspace] = settingRowsOf([state()], true, (id) => id);
  expect([inWorkspace?.here, inWorkspace?.clamped]).toEqual([null, false]);
  expect(settersOf([state()], false)).toEqual(["alice"]);
  expect(settersOf([state()], true)).toEqual([]);
});

test("a number field takes a whole number within the bounds, and says why not", () => {
  expect(numberOf(" 12 ", RANGE)).toEqual({ value: 12 });
  for (const text of ["", "1.5", "-1", "1e3", "twelve", "9999999999"]) {
    expect(numberOf(text, RANGE)).toEqual({ error: "Enter a whole number." });
  }
  expect(numberOf("1001", RANGE)).toEqual({ error: "Enter a number from 0 to 1000." });
});
