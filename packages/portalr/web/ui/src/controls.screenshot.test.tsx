/**
 * The form controls' look, pinned by screenshots (portalr ADR-0019, ADR-0037): the select closed
 * and open, fields with a hint and a refusal, a segmented filter, every button variant and size,
 * disabled too, a row with its quiet actions, and a dialog whose way out isn't "Cancel". Wide and
 * narrow, in each scheme. Like the gallery's, the baselines are Linux's, made in CI.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { dark } from "./test/colours";
import { Controls } from "./test/galleries";

async function shown(width: number) {
  await page.viewport(width, 1400);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(<Controls />);
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  await document.fonts.ready;
  await commands.pointerAway();
  return screen;
}

async function matches(name: string, target = page.getByTestId("controls")) {
  await expect(target).toMatchScreenshot(`${name}-${dark ? "dark" : "light"}`, {
    screenshotOptions: { animations: "disabled" },
  });
}

test("the controls, wide", async () => {
  await shown(900);
  await matches("controls-wide");
});

test("the controls, narrow", async () => {
  await shown(390);
  await matches("controls-narrow");
});

test("a select, open, with the choice marked", async () => {
  const screen = await shown(900);
  await screen.getByRole("combobox", { name: "Role" }).click();
  await expect.element(page.getByRole("listbox")).toBeVisible();
  await matches("controls-select-open", page.elementLocator(document.body));
});

test("the dialog whose way out is Keep running", async () => {
  const screen = await shown(900);
  await screen.getByRole("button", { name: "Cancel run run_dead" }).click();
  await expect.element(screen.getByRole("alertdialog", { name: "Cancel this run?" })).toBeVisible();
  await matches("controls-dialog", page.elementLocator(document.body));
});
