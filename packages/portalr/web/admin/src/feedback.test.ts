import { expect, test } from "vitest";
import { shownOf, unknownDays } from "./feedback";

test("the address keeps a window Feedback offers, and a workspace", () => {
  expect(shownOf({})).toEqual({ days: 7, workspace: undefined });
  expect(shownOf({ days: 30, workspace: " notes " })).toEqual({ days: 30, workspace: "notes" });
  expect(shownOf({ days: "90", workspace: "" })).toEqual({ days: 90, workspace: undefined });
  expect(shownOf({ days: 12, workspace: 3 })).toEqual({ days: 7, workspace: undefined });
});

test("the days before the first known one are unknown; none, when every day is known", () => {
  const days = ["2026-10-11", "2026-10-12", "2026-10-13"].map((day) => ({ day }));
  expect(unknownDays({ days, known_from: null })).toBe(0);
  expect(unknownDays({ days })).toBe(0);
  expect(unknownDays({ days, known_from: "2026-10-12" })).toBe(1);
  expect(unknownDays({ days, known_from: "2026-10-14" })).toBe(3);
});
