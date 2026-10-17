/**
 * Markdown's look, pinned by screenshots (portalr ADR-0019, ADR-0043): every element an agent
 * writes, wide and narrow, in each scheme, in colour-blind mode, and under forced colours, as a
 * high-contrast mode draws it. Baselines are Linux's, made in CI, with the faces loaded.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Markdown } from "./markdown";
import { dark } from "./test/colours";
import { GALLERY } from "./test/markdown";

/** The gallery laid out at a width, in a mode, with the faces loaded. */
async function shown(width: number, mode?: "colour-blind" | "forced-colours") {
  await page.viewport(width, 2400);
  onTestFinished(() => page.viewport(414, 896));
  if (mode === "colour-blind") {
    document.documentElement.dataset.cvd = "";
    onTestFinished(() => {
      delete document.documentElement.dataset.cvd;
    });
  }
  if (mode === "forced-colours") {
    await commands.forcedColors(true);
    onTestFinished(() => commands.forcedColors(false));
  }
  await render(
    <div data-testid="markdown" className="bg-surface p-4">
      <Markdown>{GALLERY}</Markdown>
    </div>,
  );
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
    document.fonts.load('1em "Fragment Mono"'),
  ]);
  await document.fonts.ready;
  await new Promise((settled) => requestAnimationFrame(() => requestAnimationFrame(settled)));
}

async function matches(name: string) {
  await expect(page.getByTestId("markdown")).toMatchScreenshot(
    `${name}-${dark ? "dark" : "light"}`,
    { screenshotOptions: { animations: "disabled" } },
  );
}

test("every element, wide", async () => {
  await shown(900);
  await matches("markdown-wide");
});

test("every element, narrow", async () => {
  await shown(390);
  await matches("markdown-narrow");
});

test("every element, in colour-blind mode", async () => {
  await shown(900, "colour-blind");
  await matches("markdown-colour-blind");
});

test("every element, under forced colours", async () => {
  await shown(900, "forced-colours");
  await matches("markdown-forced-colours");
});
