import { expect, test } from "vitest";
import { healthWindow, logWindow, onGrid, pointAt, shownOf, stepFor, stepSaid } from "./logs";

test("an address keeps the windows it offers and the ids portalr takes, and defaults the rest", () => {
  expect(shownOf({})).toEqual({
    hours: 1,
    health: 1,
    thread: undefined,
    run: undefined,
  });
  expect(shownOf({ hours: 6, health: "168", thread: " thr_1 ", run: 42 })).toEqual({
    hours: 6,
    health: 168,
    thread: "thr_1",
    run: "42",
  });
  // A day is the most Logs reads; a week is not a window of it.
  expect(shownOf({ hours: 168 }).hours).toBe(1);
  expect(shownOf({ health: 6 }).health).toBe(1);
  expect(shownOf({ thread: "a b", run: "" })).toMatchObject({ thread: undefined, run: undefined });
});

test("a logs window is whole minutes up to the next, and a health window has its step", () => {
  const now = new Date("2026-10-15T09:30:10.500Z");
  expect(logWindow(24, now)).toEqual({
    start: "2026-10-14T09:31:00.000Z",
    end: "2026-10-15T09:31:00.000Z",
  });
  expect(healthWindow(168, now)).toMatchObject({ start: "2026-10-08T09:31:00.000Z", step: 7200 });
});

test("a step keeps a chart to about ninety-six points, and is said in words", () => {
  expect([1, 24, 168].map(stepFor)).toEqual([60, 900, 7200]);
  expect(stepFor(100_000)).toBe(14_400);
  expect([15, 60, 120, 900, 3600, 7200].map(stepSaid)).toEqual([
    "15 seconds",
    "1 minute",
    "2 minutes",
    "15 minutes",
    "1 hour",
    "2 hours",
  ]);
});

test("a point is the time of day, and for a week the day too", () => {
  const seconds = Date.parse("2026-10-15T09:30:00Z") / 1000;
  expect(pointAt(seconds, 24)).toBe("09:30");
  expect(pointAt(seconds, 168)).toBe("10-15 09:30");
  // Where a zone's clock goes back an hour, two points of its are not the same in UTC.
  expect(pointAt(seconds, 24)).not.toBe(pointAt(seconds + 3600, 24));
});

test("a window's steps without a point are gaps, not joined", () => {
  const window = { start: "2026-10-15T09:00:00Z", end: "2026-10-15T09:03:00Z", step: 60 };
  const start = Date.parse(window.start) / 1000;
  const grid = onGrid(window, [
    { time: start, value: 1 },
    { time: start + 120, value: 3 },
    { time: start + 180, value: 0 },
  ]);
  expect(grid).toEqual([
    { time: start, value: 1 },
    { time: start + 60, value: null },
    { time: start + 120, value: 3 },
    { time: start + 180, value: 0 },
  ]);
  // No step, no grid.
  expect(onGrid({ start: window.start, end: window.end }, [])).toEqual([]);
});
