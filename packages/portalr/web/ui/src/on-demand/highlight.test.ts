import { afterEach, expect, test, vi } from "vitest";
import { LINE_TIME_LIMIT, tokenizer } from "./highlight";

afterEach(() => {
  vi.restoreAllMocks();
});

const LINE = 'export const day = "Friday";';

/** A line tokenized on a clock that moves `step` milliseconds each time it is read. */
async function slowly(step: number) {
  const tokenize = await tokenizer("typescript");
  let now = Date.now();
  let read = 0;
  vi.spyOn(Date, "now").mockImplementation(() => {
    read += 1;
    now += step;
    return now;
  });
  const [line = []] = tokenize(LINE).lines;
  vi.restoreAllMocks();
  return { line, read };
}

/**
 * A slow line, as a busy machine's: Shiki's own half a second cut it, and gave the rest as one
 * plain token, which a block keeps, since it tokenizes each line once (CI's flaky screenshot of a
 * note's code). The clock here moves 0.4 s a read, seconds over the line.
 */
test("a line slower than half a second is tokenized whole", async () => {
  const step = 400;
  const { line, read } = await slowly(step);
  // The clock was read, and moved well past Shiki's own half a second while the line was read.
  expect((read - 1) * step).toBeGreaterThan(2000);
  const friday = line.find((token) => token.content.includes("Friday"));
  // Not the rest of the line in one token, and in a string's colour, not the plain text's.
  expect(friday?.content).toBe('"Friday"');
  expect(friday?.color).toBe("var(--code-token-string-expression)");
  expect(line.map((token) => token.content).join("")).toBe(LINE);
});

test("a line past the limit is still cut, as a backstop for an expression that runs away", async () => {
  const { line } = await slowly(LINE_TIME_LIMIT + 1);
  // What is left after the cut is one plain token, which ends the line.
  expect(line.map((token) => token.content).join("")).toBe(LINE);
  expect(line.find((token) => token.content === '"Friday"')).toBeUndefined();
});
