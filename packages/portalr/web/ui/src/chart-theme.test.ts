import { expect, test } from "vitest";
import { formatDay, formatMoment, formatNumber } from "./chart-theme";

test("a number is written grouped, to two places at most", () => {
  expect(formatNumber(1250.5)).toBe("1,250.5");
  expect(formatNumber(0.123456)).toBe("0.12");
  expect(formatNumber(7)).toBe("7");
});

test("a day is written as an axis would, in UTC, with no year", () => {
  expect(formatDay("2026-10-15")).toBe("Oct 15");
  expect(formatDay("2026-01-01")).toBe("Jan 1");
  expect(formatDay("2025-12-31")).toBe("Dec 31");
});

test("a moment is its time of day, and, when a window spans days, its day first", () => {
  expect(formatMoment("2026-10-15 09:30", false)).toBe("09:30");
  expect(formatMoment("2026-10-15 09:30", true)).toBe("Oct 15 09:30");
});

test("what is not a day or a moment is given as it came, not thrown at", () => {
  expect(formatDay("10-15")).toBe("10-15");
  expect(formatMoment("soon", true)).toBe("soon");
  expect(formatMoment("2026-10-15T09:30:00Z", false)).toBe("2026-10-15T09:30:00Z");
});
