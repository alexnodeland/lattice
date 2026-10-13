import { expect, test } from "vitest";
import { read, refusal, SKELETON } from "./rules";

test("the skeleton is JSON, with what every stored rule needs", () => {
  const parsed = read(SKELETON);
  expect(parsed).toMatchObject({
    rule: { ordering: "none", timeout: "PT30S", when: { throttle: { at_most: 10 } } },
  });
});

test("text that isn't JSON says so", () => {
  expect(read("not json")).toEqual({ refused: expect.stringMatching(/^That isn't JSON: /) });
});

test("a refusal says what wasn't done, and each reason", () => {
  expect(
    refusal("The rule wasn't saved", {
      outcome: "refused",
      status: 422,
      reasons: ["timeout is required", "when.throttle is required"],
    }),
  ).toBe("The rule wasn't saved: timeout is required; when.throttle is required");
});
