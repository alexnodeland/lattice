import type { PortalrApi } from "@portalr/client";
import { expect, test } from "vitest";
import { byWorkspace, comments, daysIn, shownOf, thumbsByDay, trends, windowOf } from "./feedback";

type Score = PortalrApi.components["schemas"]["Score"];

const score = (at: string, value: Score["value"], extra: Partial<Score> = {}): Score => ({
  id: `${at}-${String(value)}`,
  trace_id: "t1",
  name: "thumbs",
  data_type: typeof value === "boolean" ? "BOOLEAN" : "NUMERIC",
  value,
  source: "API",
  timestamp: `${at}T12:00:00Z`,
  ...extra,
});

test("a window is whole days in UTC, ending today, the same all day", () => {
  const window = windowOf(7, new Date("2026-10-13T09:30:00Z"));
  expect(window).toEqual({ start: "2026-10-07T00:00:00.000Z", end: "2026-10-14T00:00:00.000Z" });
  expect(windowOf(7, new Date("2026-10-13T23:59:00Z"))).toEqual(window);
  expect(daysIn(window)).toEqual([
    "2026-10-07",
    "2026-10-08",
    "2026-10-09",
    "2026-10-10",
    "2026-10-11",
    "2026-10-12",
    "2026-10-13",
  ]);
});

test("people's thumbs are counted per day, and evaluators' left out", () => {
  const days = ["2026-10-12", "2026-10-13"];
  const scores = [
    score("2026-10-12", true),
    score("2026-10-12", false),
    score("2026-10-13", true),
    score("2026-10-13", true, { evaluator: "accuracy" }),
    score("2026-10-13", 1),
    score("2026-10-01", true),
  ];
  expect(thumbsByDay(scores, days)).toEqual([
    { day: "2026-10-12", up: 1, down: 1 },
    { day: "2026-10-13", up: 1, down: 0 },
  ]);
});

test("each evaluation is averaged per day, the most scored first, yes as 1 and no as 0", () => {
  const days = ["2026-10-12", "2026-10-13"];
  const scores = [
    score("2026-10-12", 0.5, { evaluator: "accuracy", name: "accuracy" }),
    score("2026-10-12", 1, { evaluator: "accuracy", name: "accuracy" }),
    score("2026-10-13", 0, { evaluator: "accuracy", name: "accuracy" }),
    score("2026-10-13", true, { evaluator: "safety", name: "safe" }),
    score("2026-10-13", "good", { evaluator: "tone", name: "tone", data_type: "CATEGORICAL" }),
    score("2026-10-13", 1),
  ];
  expect(trends(scores, days)).toEqual([
    {
      name: "accuracy · accuracy",
      count: 3,
      points: [
        { day: "2026-10-12", mean: 0.75 },
        { day: "2026-10-13", mean: 0 },
      ],
    },
    {
      name: "safety · safe",
      count: 1,
      points: [
        { day: "2026-10-12", mean: null },
        { day: "2026-10-13", mean: 1 },
      ],
    },
  ]);
});

test("each workspace's thumbs and evaluations, the busiest first, and comments newest first", () => {
  const scores = [
    score("2026-10-12", true, { workspace: "notes" }),
    score("2026-10-12", false, { workspace: "notes", comment: "wrong" }),
    score("2026-10-13", 0.5, { workspace: "plans", evaluator: "accuracy" }),
    score("2026-10-13", true, { comment: "great" }),
    score("2026-10-13", 1, { workspace: "notes" }),
  ];
  expect(byWorkspace(scores)).toEqual([
    { workspace: "notes", up: 1, down: 1, evaluated: 0 },
    { workspace: null, up: 1, down: 0, evaluated: 0 },
    { workspace: "plans", up: 0, down: 0, evaluated: 1 },
  ]);
  expect(comments(scores).map((one) => one.comment)).toEqual(["great", "wrong"]);
});

test("the address keeps a window Feedback offers, and a workspace", () => {
  expect(shownOf({})).toEqual({ days: 7 });
  expect(shownOf({ days: 30, workspace: "notes" })).toEqual({ days: 30, workspace: "notes" });
  expect(shownOf({ days: "90", workspace: "" })).toEqual({ days: 90 });
  expect(shownOf({ days: 12 })).toEqual({ days: 7 });
});
