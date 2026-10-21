import { afterEach, expect, test, vi } from "vitest";
import { tokenizer } from "./highlight";

afterEach(() => {
  vi.restoreAllMocks();
});

/**
 * A slow tokenizing, as a busy machine's or a grammar's first, cold, run is: the clock moves a
 * second each time it is read. Shiki stopped a line after half a second and gave the rest as one
 * plain token, which a block keeps, since it tokenizes each line once: a string left uncoloured
 * for good (CI's flaky screenshot of a note's code).
 */
test("a line is tokenized whole however slow tokenizing is", async () => {
  const tokenize = await tokenizer("typescript");
  let now = Date.now();
  vi.spyOn(Date, "now").mockImplementation(() => {
    now += 1000;
    return now;
  });
  const [line] = tokenize('export const day = "Friday";').lines;
  const friday = line?.find((token) => token.content.includes("Friday"));
  // Not the rest of the line in one token, and in a string's colour, not the plain text's.
  expect(friday?.content).toBe('"Friday"');
  expect(friday?.color).toBe("var(--code-token-string-expression)");
  expect(line?.map((token) => token.content).join("")).toBe('export const day = "Friday";');
});
