/**
 * The kit's look, pinned by screenshots (portalr ADR-0019): the frame with every component in it,
 * wide and narrow, in each scheme. Computed styles pin each component's colours and states; these
 * pin how they sit together, and the menu, the drawer and a dialog open. Baselines are Linux's, made in CI, with motion reduced and the
 * self-hosted faces loaded, so they don't move between runs.
 */

import { expect, onTestFinished, test } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { dark } from "./test/colours";
import { AdminGallery, Gallery, Sharing } from "./test/galleries";

/** Lay the gallery out at a width, with the faces loaded before the shot (motion is reduced). */
async function shown(width: number, height: number, dialog = false) {
  await page.viewport(width, height);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(
    <>
      <Gallery />
      {dialog && <Sharing />}
    </>,
  );
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('italic 1em "Schibsted Grotesk"'),
    document.fonts.load('1em "Fragment Mono"'),
  ]);
  return screen;
}

/** The whole page, so a menu or a drawer, which portals to the body, is in the shot. */
async function matches(name: string) {
  await expect(page.elementLocator(document.body)).toMatchScreenshot(
    `${name}-${dark ? "dark" : "light"}`,
    { screenshotOptions: { animations: "disabled" } },
  );
}

test("the frame and its components, wide", async () => {
  await shown(1280, 900);
  await matches("gallery-wide");
});

test("the frame and its components, narrow", async () => {
  await shown(390, 1400);
  await matches("gallery-narrow");
});

test("the switcher's menu, open, with the keyboard on an item", async () => {
  const screen = await shown(1280, 900);
  await screen.getByRole("button", { name: "Workspace: acme, notes" }).click();
  await userEvent.keyboard("{ArrowDown}");
  await matches("gallery-menu");
});

test("the drawer, open", async () => {
  const screen = await shown(390, 1400);
  await screen.getByRole("button", { name: "Menu" }).click();
  await expect.element(screen.getByRole("dialog", { name: "Navigation" })).toBeVisible();
  await matches("gallery-drawer");
});

test("a dialog, open, over the frame", async () => {
  const screen = await shown(1280, 900, true);
  await expect.element(screen.getByRole("dialog", { name: "Share the thread" })).toBeVisible();
  await matches("gallery-dialog");
});

test("a destructive action, asked first", async () => {
  const screen = await shown(1280, 900);
  await screen.getByRole("button", { name: "Delete acme" }).click();
  await screen.getByRole("textbox", { name: "Type acme to confirm" }).fill("acme");
  await matches("gallery-confirm");
});

test("admin's frame, with Home's cards in their states", async () => {
  await page.viewport(1280, 900);
  onTestFinished(() => page.viewport(414, 896));
  await render(<AdminGallery />);
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('1em "Fragment Mono"'),
  ]);
  await matches("gallery-admin");
});
