import { expect, test } from "vitest";
import {
  budget,
  counted,
  deploymentSpendSaid,
  dollars,
  duration,
  failuresSaid,
  feedbackSaid,
  figure,
  LIMIT,
  membersSaid,
  type ScoresReading,
  spanOf,
  spendSaid,
  unread,
  workspacesSaid,
} from "./home";

const score = (value: boolean | string, evaluator?: string) => ({
  id: `s-${Math.random()}`,
  trace_id: "t1",
  name: "thumbs.up",
  data_type: typeof value === "boolean" ? ("BOOLEAN" as const) : ("CATEGORICAL" as const),
  value,
  source: "API",
  timestamp: "2026-10-12T00:00:00Z",
  ...(evaluator && { evaluator }),
});

test("a tool that didn't answer, or isn't configured, says so with a shape and a word", () => {
  expect(unread("Langfuse", { status: "unavailable", reason: "timed out" })).toEqual({
    figure: null,
    line: "Langfuse isn't answering: timed out",
    badge: { tone: "failed", word: "Unavailable" },
  });
  expect(unread("LiteLLM", { status: "unconfigured" })).toEqual({
    figure: null,
    line: "LiteLLM isn't configured.",
    badge: { tone: "stopped", word: "Not configured" },
  });
});

test("a span runs to this second, over the days before it", () => {
  const now = new Date("2026-10-12T14:37:12.345Z");
  expect(spanOf(now, 1, 86_400)).toEqual({
    start: "2026-10-11T14:37:12.000Z",
    end: "2026-10-12T14:37:12.000Z",
    step: 86_400,
  });
  expect(spanOf(now, 7)).toEqual({
    start: "2026-10-05T14:37:12.000Z",
    end: "2026-10-12T14:37:12.000Z",
  });
});

test("figures are grouped, and a capped one shows it may be more", () => {
  expect(figure(1234)).toBe("1,234");
  expect(figure(999, LIMIT)).toBe("999");
  expect(figure(1000, LIMIT)).toBe("1,000+");
  expect(counted(1, "member")).toBe("1 member");
  expect(counted(2, "person", "people")).toBe("2 people");
  expect(dollars(1234.5)).toBe("$1,234.50");
});

test("members are counted as people and service principals", () => {
  expect(
    membersSaid([
      { kind: "user", id: "alice" },
      { kind: "user", id: "bob" },
      { kind: "service_principal", id: "ci" },
    ]),
  ).toEqual({ figure: "3", line: "2 people and 1 service principal" });
  expect(workspacesSaid(["notes", "plans"])).toEqual({
    figure: "2",
    line: "with a log you can open in artifactr",
  });
});

test("feedback is people's alone: N pieces, and x of y thumbs up", () => {
  const reading: ScoresReading = {
    status: "ok",
    data: [score(true), score(true), score(false), score("good"), score(true, "accuracy")],
  };
  expect(feedbackSaid(reading)).toEqual({
    figure: "4",
    line: "pieces of feedback in the last week; 2 of 3 thumbs up",
  });
  expect(feedbackSaid({ status: "ok", data: [score("good")] })).toEqual({
    figure: "1",
    line: "pieces of feedback in the last week",
  });
  expect(feedbackSaid({ status: "unconfigured" }).badge?.word).toBe("Not configured");
});

test("failed turns are the last point's count, of the day before it", () => {
  expect(
    failuresSaid({
      status: "ok",
      data: [
        { time: 1, value: 0 },
        { time: 2, value: 3.0000001 },
      ],
    }),
  ).toEqual({ figure: "3", line: "in the last day" });
  expect(failuresSaid({ status: "ok", data: [] })).toEqual({
    figure: "0",
    line: "in the last day",
  });
  expect(failuresSaid({ status: "unavailable", reason: "down" }).badge?.tone).toBe("failed");
});

test("a budget is under, near from 80%, over past it, or none", () => {
  expect(budget({ spend: 10 })).toBe("none");
  expect(budget({ spend: 10, max_budget: 0 })).toBe("none");
  expect(budget({ spend: 10, max_budget: 100 })).toBe("under");
  expect(budget({ spend: 80, max_budget: 100 })).toBe("near");
  expect(budget({ spend: 101, max_budget: 100 })).toBe("over");
});

test("LiteLLM's budget durations read as words", () => {
  expect(duration("30d")).toBe("30 days");
  expect(duration("1d")).toBe("day");
  expect(duration("1mo")).toBe("month");
  expect(duration("12h")).toBe("12 hours");
  expect(duration("weekly")).toBe("weekly");
});

test("spend is $X of $Y with its budget's badge, or says why there's no figure", () => {
  const spent = (spend: number, max_budget?: number, budget_duration?: string) => ({
    status: "ok" as const,
    data: { spend, max_budget: max_budget ?? null, budget_duration: budget_duration ?? null },
  });
  expect(spendSaid(spent(85, 100, "30d"))).toEqual({
    figure: "$85.00",
    line: "of $100.00, every 30 days",
    badge: { tone: "near", word: "Near budget" },
  });
  expect(spendSaid(spent(120, 100))).toEqual({
    figure: "$120.00",
    line: "of $100.00",
    badge: { tone: "over", word: "Over budget" },
  });
  expect(spendSaid(spent(10, 100))).toEqual({ figure: "$10.00", line: "of $100.00" });
  expect(spendSaid(spent(10))).toEqual({ figure: "$10.00", line: "No budget is set." });
  expect(spendSaid({ status: "ok", data: null })).toEqual({
    figure: null,
    line: "The tenant has no team in LiteLLM yet.",
  });
});

test("the deployment's spend is every tenant's together", () => {
  expect(
    deploymentSpendSaid({
      status: "ok",
      data: [
        { tenant: "acme", spend: 10 },
        { tenant: "globex", spend: 2.5 },
      ],
    }),
  ).toEqual({ figure: "$12.50", line: "across every tenant's LiteLLM team" });
  expect(deploymentSpendSaid({ status: "unconfigured" }).line).toBe("LiteLLM isn't configured.");
});
