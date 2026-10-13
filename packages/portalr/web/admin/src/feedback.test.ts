import { expect, test } from "vitest";
import { shownOf, windowOf } from "./feedback";

test("a window is whole days in UTC, ending today, the same all day", () => {
  const window = windowOf(7, new Date("2026-10-13T09:30:00Z"));
  expect(window).toEqual({ start: "2026-10-07T00:00:00.000Z", end: "2026-10-14T00:00:00.000Z" });
  expect(windowOf(7, new Date("2026-10-13T23:59:00Z"))).toEqual(window);
});

test("the address keeps a window Feedback offers, and a workspace", () => {
  expect(shownOf({})).toEqual({ days: 7, workspace: undefined });
  expect(shownOf({ days: 30, workspace: " notes " })).toEqual({ days: 30, workspace: "notes" });
  expect(shownOf({ days: "90", workspace: "" })).toEqual({ days: 90, workspace: undefined });
  expect(shownOf({ days: 12, workspace: 3 })).toEqual({ days: 7, workspace: undefined });
});
