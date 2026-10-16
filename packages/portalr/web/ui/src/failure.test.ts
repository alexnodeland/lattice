import { expect, test } from "vitest";
import { failureSaid } from "./failure";

test("a failure's message starts its own sentence with a capital", () => {
  expect(failureSaid(new Error("the server refused the read (422): no"))).toBe(
    "The server refused the read (422): no",
  );
  expect(failureSaid("down")).toBe("Down");
  expect(failureSaid(new Error(""))).toBe("");
});
