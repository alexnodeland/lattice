import { defaultRehypePlugins } from "streamdown";
import { expect, test } from "vitest";

test("Streamdown's rehype-raw is the stub, as the UIs build it, not the plugin that parses HTML", () => {
  // The real plugin returns a transformer that parses HTML with parse5; the stub, nothing.
  const raw = defaultRehypePlugins.raw as unknown as (options?: unknown) => unknown;
  expect(raw({})).toBeUndefined();
});
