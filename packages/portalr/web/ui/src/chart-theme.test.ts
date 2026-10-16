import { expect, test } from "vitest";
import { cut, formatDay, formatMoment, formatNumber, LONGEST_LABEL } from "./chart-theme";

test("a number is written grouped, to two places at most", () => {
  expect(formatNumber(1250.5)).toBe("1,250.5");
  expect(formatNumber(0.123456)).toBe("0.12");
  expect(formatNumber(7)).toBe("7");
});

test("a day is written as an axis would, in UTC, with no year, whatever the zone", () => {
  expect(formatDay("2026-10-15")).toBe("Oct 15");
  expect(formatDay("2026-01-01")).toBe("Jan 1");
  expect(formatDay("2025-12-31")).toBe("Dec 31");
});

test("a moment is its time of day, and, when a window spans days, its day first", () => {
  expect(formatMoment("2026-10-15 09:30", false)).toBe("09:30");
  expect(formatMoment("2026-10-15 09:30", true)).toBe("Oct 15 09:30");
});

test("a long name is cut to its limit, with an ellipsis, and a short one is kept", () => {
  expect(cut("Thumbs down")).toBe("Thumbs down");
  const cutName = cut("an evaluation with a long name");
  expect(cutName).toHaveLength(LONGEST_LABEL);
  expect(cutName.endsWith("…")).toBe(true);
});
