import { expect, test } from "vitest";
import { budget, counted, dollars, failures, unread, windowOf } from "./home";

test("a tool that didn't answer, or isn't configured, says so on its card alone", () => {
  expect(unread("Langfuse", { status: "ok", data: [] })).toBeNull();
  expect(unread("Langfuse", { status: "unavailable", reason: "timed out" })).toEqual({
    figure: null,
    line: "Langfuse isn't answering: timed out",
  });
  expect(unread("LiteLLM", { status: "unconfigured" })).toEqual({
    figure: null,
    line: "LiteLLM isn't configured.",
  });
});

test("a window runs to this minute, over the days before it", () => {
  const now = new Date("2026-10-12T14:37:12.345Z");
  expect(windowOf(now, 1, 300)).toEqual({
    start: "2026-10-11T14:37:00.000Z",
    end: "2026-10-12T14:37:00.000Z",
    step: 300,
  });
  expect(windowOf(now, 7)).toEqual({
    start: "2026-10-05T14:37:00.000Z",
    end: "2026-10-12T14:37:00.000Z",
  });
});

test("failures are the rates held for their steps, rounded", () => {
  expect(failures([], 3600)).toBe(0);
  expect(
    failures(
      [
        { time: 0, value: 0.001 },
        { time: 1, value: 0.0005 },
      ],
      3600,
    ),
  ).toBe(5);
});

test("a budget is under, near from 80%, over past it, or none", () => {
  expect(budget({ spend: 10 })).toBe("none");
  expect(budget({ spend: 10, max_budget: 0 })).toBe("none");
  expect(budget({ spend: 10, max_budget: 100 })).toBe("under");
  expect(budget({ spend: 80, max_budget: 100 })).toBe("near");
  expect(budget({ spend: 101, max_budget: 100 })).toBe("over");
});

test("money is in dollars, and counts take their noun's number", () => {
  expect(dollars(1234.5)).toBe("$1,234.50");
  expect(counted(1, "member")).toBe("1 member");
  expect(counted(3, "member")).toBe("3 members");
  expect(counted(2, "person", "people")).toBe("2 people");
});
