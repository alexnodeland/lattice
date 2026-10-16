import { expect, test } from "vitest";
import { daysOf, windowOf } from "./window";

test("a window is whole days in UTC, ending today, the same all day", () => {
  const window = windowOf(7, new Date("2026-10-13T09:30:00Z"));
  expect(window).toEqual({ start: "2026-10-07T00:00:00.000Z", end: "2026-10-14T00:00:00.000Z" });
  expect(windowOf(7, new Date("2026-10-13T23:59:00Z"))).toEqual(window);
});

test("the address's window is one offered, or the default", () => {
  expect(daysOf(undefined)).toBe(7);
  expect(daysOf("90")).toBe(90);
  expect(daysOf(12)).toBe(7);
});
