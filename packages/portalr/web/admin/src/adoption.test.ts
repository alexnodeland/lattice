import { expect, test } from "vitest";
import { shareOf, shownOf, stepsOf, weekSaid, weeksOf } from "./adoption";

test("the address's window is one offered, or a week", () => {
  expect(shownOf({ days: "30" })).toEqual({ days: 30 });
  expect(shownOf({ days: "31" })).toEqual({ days: 7 });
  expect(shownOf({})).toEqual({ days: 7 });
});

test("a share is a whole percent, and none of none is a dash", () => {
  expect(shareOf(2, 3)).toBe("67%");
  expect(shareOf(0, 0)).toBe("–");
});

test("the funnel's steps are in order, each named for what people did", () => {
  expect(stepsOf({ page: 3, thread: 2, message: 1 }).map((step) => step.name)).toEqual([
    "Viewed a page",
    "Then opened a thread",
    "Then sent a message",
  ]);
});

test("each week of retention is numbered from one", () => {
  expect(weeksOf([4, 2]).map((week) => `${weekSaid(week.week)}: ${week.people}`)).toEqual([
    "Week 1: 4",
    "Week 2: 2",
  ]);
});
