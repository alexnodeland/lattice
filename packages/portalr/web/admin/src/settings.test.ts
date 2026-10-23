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

test("a setting is named by what it limits, by its key, never the key itself", () => {
  expect(nameOf(state())).toBe("FreeCAD's tries an hour");
  expect(nameOf(state({ key: "connect-per-hour:blender" }))).toBe("Blender's tries an hour");
  expect(nameOf(state({ key: "new:one", description: "Days logs are kept." }))).toBe(
    "Days logs are kept.",
  );
});

test("a clamped value says why: the settings now allow more, or less", () => {
  const [lowered] = settingRowsOf([state()], false, (id) => id);
  expect(lowered?.clamped).toBe(
    "What is set here doesn't apply: 60 does, as no more is allowed now.",
  );
  const raised = state({
    kind: { type: "int_range", low: 10, high: 1000, universe: null },
    tenant: {
      value: 5,
      version: 1,
      by: { kind: "user", id: "a" },
      at: "2026-10-22T09:00:00Z",
      clamped: true,
    },
    effective: 10,
  });
  expect(settingRowsOf([raised], false, (id) => id)[0]?.clamped).toBe(
    "The settings now allow at least 10: 10 applies.",
  );
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
    clamped: "What is set here doesn't apply: 60 does, as no more is allowed now.",
    version: 3,
    inherits: "the operator's",
  });
  const [unset] = settingRowsOf([state({ operator: null })], false, (id) => id);
  expect(unset?.inherits).toBe("the default");
  expect(row?.here?.value).toBe(90);
  const [inWorkspace] = settingRowsOf([state()], true, (id) => id);
  expect([inWorkspace?.here, inWorkspace?.clamped]).toEqual([null, null]);
  expect(settersOf([state()], false)).toEqual(["alice"]);
  expect(settersOf([state()], true)).toEqual([]);
});

test("a number field takes a whole number within the level's range, and says why not", () => {
  expect(numberOf(" 12 ", 0, 30)).toEqual({ value: 12 });
  for (const text of ["", "1.5", "-1", "1e3", "twelve", "9999999999"]) {
    expect(numberOf(text, 10, 30)).toEqual({ error: "Enter a whole number from 10 to 30." });
  }
  expect(numberOf("31", 10, 30)).toEqual({ error: "Enter a whole number from 10 to 30." });
  expect(numberOf("5", 10, 30)).toHaveProperty("error");
});
