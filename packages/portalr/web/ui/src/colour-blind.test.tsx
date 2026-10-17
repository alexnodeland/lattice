import { afterEach, beforeEach, expect, onTestFinished, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { useColourBlind } from "./colour-blind";

const KEY = "portalr-colour-blind";

function Mode() {
  const [on, setOn] = useColourBlind();
  return (
    <button type="button" onClick={() => setOn(!on)}>
      {on ? "on" : "off"}
    </button>
  );
}

beforeEach(() => {
  localStorage.removeItem(KEY);
  delete document.documentElement.dataset.cvd;
});

afterEach(() => {
  localStorage.removeItem(KEY);
  delete document.documentElement.dataset.cvd;
  vi.restoreAllMocks();
});

test("it starts off, with nothing chosen", async () => {
  const screen = await render(<Mode />);
  await expect.element(screen.getByRole("button", { name: "off" })).toBeVisible();
  expect(document.documentElement.hasAttribute("data-cvd")).toBe(false);
});

test("turning it on sets data-cvd on the root and keeps the choice; turning it off takes both away", async () => {
  const screen = await render(<Mode />);
  await screen.getByRole("button", { name: "off" }).click();
  expect(document.documentElement.hasAttribute("data-cvd")).toBe(true);
  expect(localStorage.getItem(KEY)).toBe("on");
  await screen.getByRole("button", { name: "on" }).click();
  expect(document.documentElement.hasAttribute("data-cvd")).toBe(false);
  expect(localStorage.getItem(KEY)).toBeNull();
});

test("a kept choice is what a new page starts on", async () => {
  localStorage.setItem(KEY, "on");
  const screen = await render(<Mode />);
  await expect.element(screen.getByRole("button", { name: "on" })).toBeVisible();
});

test("without storage the choice lasts as long as the page, and nothing throws", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  onTestFinished(() => {
    vi.restoreAllMocks();
  });
  const screen = await render(<Mode />);
  await expect.element(screen.getByRole("button", { name: "off" })).toBeVisible();
  await screen.getByRole("button", { name: "off" }).click();
  expect(document.documentElement.hasAttribute("data-cvd")).toBe(true);
  await expect.element(screen.getByRole("button", { name: "on" })).toBeVisible();
});

/** ui's scheme.js, run as a page runs it before its first paint. */
async function paint() {
  const script = await (await fetch("/scheme.js")).text();
  new Function(script)();
}

test("before the first paint, scheme.js sets the mode a person kept, and nothing otherwise", async () => {
  await paint();
  expect(document.documentElement.hasAttribute("data-cvd")).toBe(false);
  localStorage.setItem(KEY, "on");
  await paint();
  expect(document.documentElement.hasAttribute("data-cvd")).toBe(true);
});

test("scheme.js without storage leaves the page as it is", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  onTestFinished(() => {
    vi.restoreAllMocks();
  });
  await expect(paint()).resolves.toBeUndefined();
  expect(document.documentElement.hasAttribute("data-cvd")).toBe(false);
});
