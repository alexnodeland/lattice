import { expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { useHighlighted } from "./highlighting";

/**
 * What each call to the tokenizer was given: each must be code not tokenized before. And when the
 * tokenizer has loaded: its grammar is fetched and compiled lazily, which a loaded runner takes
 * more than a second over, so a test waits on that rather than on a poll's default second.
 */
const { given, loaded, ready } = vi.hoisted(() => {
  let ready = () => {};
  const loaded = new Promise<void>((resolve) => {
    ready = resolve;
  });
  return { given: [] as string[], loaded, ready: () => ready() };
});

vi.mock(import("./on-demand/highlight"), async (actual) => {
  const real = await actual();
  return {
    ...real,
    tokenizer: async (language) => {
      const tokenize = await real.tokenizer(language);
      ready();
      return (code, after) => {
        given.push(code);
        return tokenize(code, after);
      };
    },
  };
});

function Code({ code, complete }: { code: string; complete: boolean }) {
  return <pre>{useHighlighted(code, "py", complete) ?? "plain"}</pre>;
}

test("a block is tokenized a whole line at a time as it arrives, and never again once it has", async () => {
  given.length = 0;
  const screen = await render(<Code code={"a = 1\nb ="} complete={false} />);
  await loaded;
  await expect.poll(() => screen.container.querySelector("span")).not.toBeNull();
  await screen.rerender(<Code code={"a = 1\nb = 2\nc"} complete={false} />);
  await screen.rerender(<Code code={"a = 1\nb = 2\nc = 3"} complete={true} />);
  await screen.rerender(<Code code={"a = 1\nb = 2\nc = 3"} complete={true} />);
  await screen.rerender(<Code code={"a = 1\nb = 2\nc = 3"} complete={true} />);
  expect(given).toEqual(["a = 1", "b = 2", "c = 3"]);
  expect(screen.container.textContent).toBe("a = 1\nb = 2\nc = 3");
});

test("a block that changes other than at its end is tokenized again from its start", async () => {
  given.length = 0;
  const screen = await render(<Code code={"x = 1"} complete={true} />);
  await loaded;
  await expect.poll(() => given.length).toBe(1);
  await screen.rerender(<Code code={"y = 1"} complete={true} />);
  expect(given).toEqual(["x = 1", "y = 1"]);
});

test("a block longer than is highlighted shows as it is", async () => {
  given.length = 0;
  const long = "x = 1\n".repeat(4000);
  const screen = await render(<Code code={long} complete={true} />);
  // Loaded, so "plain" is the length's doing, not a grammar still on its way.
  await loaded;
  await new Promise((settled) => setTimeout(settled, 50));
  expect(screen.container.textContent).toBe("plain");
  expect(given).toEqual([]);
});
