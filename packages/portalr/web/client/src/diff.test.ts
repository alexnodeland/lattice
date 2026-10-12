import { expect, test } from "vitest";
import { BOUND, changes } from "./diff";

test("prose changes by word", () => {
  expect(changes("Launch on Monday.", "Launch on Tuesday.", "words")).toEqual([
    { kind: "same", text: "Launch on " },
    { kind: "removed", text: "Monday" },
    { kind: "added", text: "Tuesday" },
    { kind: "same", text: "." },
  ]);
});

test("structured text changes by line", () => {
  expect(changes("a: 1\nb: 2\n", "a: 1\nb: 3\n", "lines")).toEqual([
    { kind: "same", text: "a: 1\n" },
    { kind: "removed", text: "b: 2\n" },
    { kind: "added", text: "b: 3\n" },
  ]);
});

test("the same text is one kept run", () => {
  expect(changes("same", "same", "words")).toEqual([{ kind: "same", text: "same" }]);
});

test("changes too large to find are none, rather than a stall", () => {
  const words = (prefix: string) =>
    Array.from({ length: BOUND.maxEditLength + 10 }, (_, n) => `${prefix}${n}`).join(" ");
  expect(changes(words("a"), words("b"), "words")).toBeNull();
});
