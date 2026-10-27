import { expect, test } from "vitest";
import { renderHook } from "vitest-browser-react";
import { retry, useLoaded, useRetrying } from "./on-demand";

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

test("an add-on that failed is tried again when what wants it changes, and not otherwise", async () => {
  let tries = 0;
  const load = async () => {
    tries += 1;
    throw new TypeError("Failed to fetch dynamically imported module");
  };
  const { result, rerender } = await renderHook(
    (props?: { wanted: boolean; key: string }) =>
      useRetrying(load, props?.wanted ?? true, props?.key ?? "run_1"),
    { initialProps: { wanted: true, key: "run_1" } },
  );
  await expect.poll(() => tries).toBe(1);
  expect(result.current).toBeNull();
  await rerender({ wanted: true, key: "run_1" });
  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(tries).toBe(1);
  await rerender({ wanted: true, key: "run_2" });
  await expect.poll(() => tries).toBe(2);
  // Not wanted, it isn't tried, whatever changes.
  await rerender({ wanted: false, key: "run_3" });
  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(tries).toBe(2);
});
