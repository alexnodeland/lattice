import { expect, test } from "vitest";
import { renderHook } from "vitest-browser-react";
import { retry, useLoaded } from "./on-demand";

test("an add-on is nothing until it loads, then its module", async () => {
  const load = async () => ({ drawn: true });
  const { result } = await renderHook(() => useLoaded(load));
  await expect
    .poll(() => result.current)
    .toEqual({
      module: { drawn: true },
      failed: false,
      error: null,
    });
});

test("an add-on that won't load says it failed, once and for whoever asks after", async () => {
  const refused = new TypeError("Failed to fetch");
  const load = () => Promise.reject(refused);
  const first = await renderHook(() => useLoaded(load));
  await expect
    .poll(() => first.result.current)
    .toEqual({ module: null, failed: true, error: refused });
  const later = await renderHook(() => useLoaded(load));
  expect(later.result.current).toEqual({ module: null, failed: true, error: refused });
});

test("an add-on not wanted isn't loaded, and is nothing", async () => {
  let asked = 0;
  const load = async () => {
    asked += 1;
    return {};
  };
  const { result } = await renderHook(() => useLoaded(load, false));
  expect(result.current).toEqual({ module: null, failed: false, error: null });
  expect(asked).toBe(0);
});

test("an add-on that failed loads again when retried, and one loaded isn't loaded twice", async () => {
  let asked = 0;
  const load = () => {
    asked += 1;
    return asked === 1
      ? Promise.reject(new TypeError("Failed to fetch"))
      : Promise.resolve({ drawn: true });
  };
  const { result } = await renderHook(() => useLoaded(load));
  await expect.poll(() => result.current.failed).toBe(true);
  retry(load);
  await expect.poll(() => result.current.module).toEqual({ drawn: true });
  expect(result.current.failed).toBe(false);
  retry(load);
  expect(asked).toBe(2);
});
