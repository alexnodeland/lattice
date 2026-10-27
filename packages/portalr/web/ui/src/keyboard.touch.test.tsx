/**
 * The on-screen keyboard on a phone (portalr ADR-0082): what it covers, as the visual viewport
 * says, is kept on the root, and the composer's dock sits above it, so Send is never under it.
 */

import { afterEach, expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { ComposerDock } from "./composer-dock";

const real = window.visualViewport;
afterEach(() =>
  Object.defineProperty(window, "visualViewport", { value: real, configurable: true }),
);

test("the composer's dock rises by what the keyboard covers, and settles when it goes", async () => {
  const viewport = new EventTarget() as EventTarget & { height: number; offsetTop: number };
  viewport.height = window.innerHeight;
  viewport.offsetTop = 0;
  Object.defineProperty(window, "visualViewport", { value: viewport, configurable: true });
  const screen = await render(
    <div style={{ height: "300vh" }}>
      <ComposerDock>
        <button type="submit">Send</button>
      </ComposerDock>
    </div>,
  );
  const dock = screen.getByText("Send").element().parentElement as HTMLElement;
  // The touch module loads on first need.
  await expect
    .poll(() => document.documentElement.style.getPropertyValue("--keyboard-inset"))
    .toBe("0px");
  viewport.height = window.innerHeight - 300;
  viewport.dispatchEvent(new Event("resize"));
  await expect
    .poll(() => document.documentElement.style.getPropertyValue("--keyboard-inset"))
    .toBe("300px");
  expect(getComputedStyle(dock).bottom).toBe("300px");
  // The home indicator is under the keyboard: nothing kept clear for it.
  expect(document.documentElement.hasAttribute("data-keyboard")).toBe(true);
  viewport.height = window.innerHeight;
  viewport.dispatchEvent(new Event("resize"));
  await expect.poll(() => getComputedStyle(dock).bottom).toBe("0px");
  expect(document.documentElement.hasAttribute("data-keyboard")).toBe(false);
});
