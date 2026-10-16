import { expect, test } from "vitest";
import { isId, shownOf, startedAt, windowOf } from "./traces";

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
