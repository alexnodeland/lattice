import { expect, test } from "vitest";
import { renderHook } from "vitest-browser-react";
import { useLoaded } from "./on-demand";

test("an add-on is nothing until it loads, then its module", async () => {
  const load = async () => ({ drawn: true });
  const { result } = await renderHook(() => useLoaded(load));
  await expect.poll(() => result.current).toEqual({ module: { drawn: true }, failed: false });
});

test("an add-on that won't load says it failed, once and for whoever asks after", async () => {
  const load = () => Promise.reject(new TypeError("Failed to fetch"));
  const first = await renderHook(() => useLoaded(load));
  await expect.poll(() => first.result.current).toEqual({ module: null, failed: true });
  const later = await renderHook(() => useLoaded(load));
  expect(later.result.current).toEqual({ module: null, failed: true });
});

test("an add-on not wanted isn't loaded, and is nothing", async () => {
  let asked = 0;
  const load = async () => {
    asked += 1;
    return {};
  };
  const { result } = await renderHook(() => useLoaded(load, false));
  expect(result.current).toEqual({ module: null, failed: false });
  expect(asked).toBe(0);
});
