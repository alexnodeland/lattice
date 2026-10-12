import { expect, test } from "vitest";
import { type Feedback, thumbs } from "./feedback";

const given = (id: string, value: Record<string, unknown>, type = "thumbs"): Feedback => ({
  actor: { kind: "user", id },
  type,
  value,
});

test("a person's thumbs are their latest, with why, and nobody else's", () => {
  expect(
    thumbs(
      [given("alice", { up: true }), given("alice", { up: false, comment: "Wrong" })],
      "alice",
    ),
  ).toEqual({
    up: false,
    comment: "Wrong",
  });
  expect(thumbs([given("alice", { up: true, comment: "" })], "alice")).toEqual({
    up: true,
    comment: null,
  });
  expect(thumbs([given("bob", { up: true })], "alice")).toBeNull();
  expect(
    thumbs([{ actor: { kind: "system" }, type: "thumbs", value: { up: true } }], "alice"),
  ).toBeNull();
});

test("feedback that isn't thumbs, or isn't up or down, isn't thumbs", () => {
  expect(thumbs([given("alice", { up: "yes" })], "alice")).toBeNull();
  expect(thumbs([given("alice", { stars: 5 }, "rating")], "alice")).toBeNull();
  expect(thumbs([], "alice")).toBeNull();
});
