import { expect, test } from "vitest";
import { newestFirst } from "./order";

test("newest first, by the moment however it is written, ties and unreadable moments by id", () => {
  const listed = [
    { id: "b", changedAt: "not a moment" },
    { id: "c", changedAt: "2026-10-21T12:00:00Z" },
    { id: "a", changedAt: "2026-10-21T14:00:00+02:00" },
    { id: "d", changedAt: "2026-10-21T13:00:00Z" },
    { id: "e", changedAt: "" },
  ];
  // "a" and "c" are one moment, written with two offsets: by id. Unreadable ones last, by id.
  expect([...listed].sort(newestFirst).map((each) => each.id)).toEqual(["d", "a", "c", "b", "e"]);
  // A total order: the same whichever way round the list starts.
  expect(
    [...listed]
      .reverse()
      .sort(newestFirst)
      .map((each) => each.id),
  ).toEqual(["d", "a", "c", "b", "e"]);
});
