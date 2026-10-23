import { expect, test } from "vitest";
import {
  ANALYTICS_ATTRIBUTE,
  analyticsSessionOf,
  isId,
  shownOf,
  startedAt,
  windowOf,
} from "./traces";

test("a window ends at the next whole minute, so a read holds a minute", () => {
  const first = windowOf(1, new Date("2026-10-15T09:30:10.500Z"));
  expect(first).toEqual({ start: "2026-10-15T08:31:00.000Z", end: "2026-10-15T09:31:00.000Z" });
  expect(windowOf(1, new Date("2026-10-15T09:30:59.999Z"))).toEqual(first);
  expect(windowOf(168, new Date("2026-10-15T09:31:00.000Z")).start).toBe(
    "2026-10-08T09:31:00.000Z",
  );
});

test("the address keeps a window Traces offers, and the ids portalr takes", () => {
  expect(shownOf({})).toEqual({ hours: 1, thread: undefined, run: undefined });
  expect(shownOf({ hours: "24", thread: " thr_1 ", run: 42 })).toEqual({
    hours: 24,
    thread: "thr_1",
    run: "42",
  });
  expect(shownOf({ hours: 5, thread: "a b", run: "x".repeat(129) })).toEqual({
    hours: 1,
    thread: undefined,
    run: undefined,
  });
  expect(shownOf({ thread: "run_1:a@b-c.d", run: true, hours: 168 })).toEqual({
    hours: 168,
    thread: "run_1:a@b-c.d",
    run: undefined,
  });
  // An id is what portalr's reads take: no spaces, nothing but letters, digits and _.:@-.
  expect(["thr_1", "a.b:c@d-e", "0"].every(isId)).toBe(true);
  expect(["", " ", "a b", "-a", "a/b", "a,b", "é"].some(isId)).toBe(false);
});

test("a trace's start is the moment its nanoseconds say", () => {
  expect(startedAt(1_792_105_139_940_000_000)).toBe("2026-10-15T22:58:59.940Z");
});

test("an analytics session in the address is kept only where the relay could have made it", () => {
  expect(shownOf({ analytics: "1792800000-0123456789abcdef" }).analytics).toBe(
    "1792800000-0123456789abcdef",
  );
  for (const wrong of ["", "thr_1", "1-0123456789ABCDEF", 42]) {
    expect(shownOf({ analytics: wrong }).analytics).toBeUndefined();
  }
});

test("a trace's analytics session is the first its spans name, where it is one", () => {
  const span = (session?: unknown) => ({
    attributes: session === undefined ? {} : { [ANALYTICS_ATTRIBUTE]: session },
  });
  expect(analyticsSessionOf([span(), span("1-0123456789abcdef")])).toBe("1-0123456789abcdef");
  expect(analyticsSessionOf([span("x"), span(7)])).toBeUndefined();
});
