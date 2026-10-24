/**
 * A diagram's card and its canvas under portalr's Content-Security-Policy, in Chromium: the canvas
 * loaded only when opened, drawn with no violation of the policy, no WebAssembly, and no request to
 * any origin but the page's own; reached and left by the keyboard, its focus kept in it while it is
 * open and given back to the button that opened it (portalr ADR-0072, ADR-0068).
 */

import { type Browser, chromium, type Page } from "playwright";
import { afterAll, beforeAll, expect, test } from "vitest";
import { open } from "./harness";

let browser: Browser;

beforeAll(async () => {
  browser = await chromium.launch();
});

afterAll(() => browser.close());

/** Every request the page makes, and the ones to an origin but its own. */
function requests(page: Page, origin: string) {
  const made: string[] = [];
  page.on("request", (request) => made.push(request.url()));
  return {
    made,
    away: () =>
      made.filter(
        (url) => !url.startsWith(origin) && !url.startsWith("data:") && !url.startsWith("blob:"),
      ),
  };
}

test("the card loads no canvas until it is opened, and the canvas keeps to the policy", async () => {
  const { page, reported } = await open(browser);
  const origin = new URL(page.url()).origin;
  const seen = requests(page, origin);
  await page.goto(`${origin}/?diagram`);
  const opener = page.getByRole("button", { name: "Open canvas" });
  await opener.waitFor();
  expect(seen.made.filter((url) => /canvas/.test(url))).toEqual([]);
  // The text version is text: the label's markup is shown, never run.
  await page.getByRole("button", { name: "Text version" }).click();
  await expect.poll(() => page.getByText("<script>alert(1)</script>").count()).toBe(1);
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "Stack" });
  await dialog.waitFor();
  await page.locator(".excalidraw canvas").first().waitFor();
  // Its faces load, from the page's own copy of them.
  await expect
    .poll(() => seen.made.some((url) => url.startsWith(`${origin}/excalidraw/fonts/`)))
    .toBe(true);
  await page.evaluate(() => document.fonts.ready);
  await page.mouse.move(400, 300);
  await page.mouse.wheel(0, 200);
  expect(seen.made.some((url) => /canvas/.test(url))).toBe(true);
  expect(seen.away()).toEqual([]);
  expect(await reported()).toEqual([]);
  await page.context().close();
});

test("the canvas is reached and left by the keyboard, and gives the focus back", async () => {
  const { page, reported } = await open(browser, "?diagram");
  const opener = page.getByRole("button", { name: "Open canvas" });
  await opener.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Stack" });
  await dialog.waitFor();
  await page.locator(".excalidraw canvas").first().waitFor();
  expect(await dialog.getAttribute("aria-modal")).toBe("true");
  // Tab, however far, stays in the dialog.
  for (let step = 0; step < 25; step += 1) {
    await page.keyboard.press("Tab");
    expect(
      await page.evaluate(() => document.activeElement?.closest("[role=dialog]") !== null),
    ).toBe(true);
  }
  for (let step = 0; step < 5; step += 1) {
    await page.keyboard.press("Shift+Tab");
    expect(
      await page.evaluate(() => document.activeElement?.closest("[role=dialog]") !== null),
    ).toBe(true);
  }
  // Escape leaves it, with nothing selected on the canvas, and the focus is the opener's again.
  await page.keyboard.press("Escape");
  await dialog.waitFor({ state: "detached" });
  expect(await page.evaluate(() => document.activeElement?.textContent)).toBe("Open canvas");
  // And so does its Close button.
  await page.keyboard.press("Enter");
  await dialog.waitFor();
  await dialog.getByRole("button", { name: "Close canvas" }).click();
  await dialog.waitFor({ state: "detached" });
  expect(await page.evaluate(() => document.activeElement?.textContent)).toBe("Open canvas");
  expect(await reported()).toEqual([]);
  await page.context().close();
});
