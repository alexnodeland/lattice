/**
 * The offer of a new version, and the notice of a tab whose build is gone, pinned by screenshots
 * (portalr ADR-0058): wide and narrow, in both schemes.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { NewVersion } from "./new-version";
import { dark } from "./test/colours";

for (const [name, width, stale] of [
  ["wide", 900, false],
  ["narrow", 390, false],
  ["stale-wide", 900, true],
  ["stale-narrow", 390, true],
] as const) {
  test(`a new version offered, ${name}`, async () => {
    await page.viewport(width, 300);
    onTestFinished(() => page.viewport(414, 896));
    const screen = await render(
      <div className="h-40 bg-paper">
        <NewVersion ui="app" stale={stale} onReload={() => {}} onDismiss={() => {}} />
      </div>,
    );
    await document.fonts.ready;
    await commands.pointerAway();
    await expect(
      page.elementLocator(screen.container.firstElementChild?.firstElementChild as Element),
    ).toMatchScreenshot(`new-version-${name}-${dark ? "dark" : "light"}`, {
      screenshotOptions: { animations: "disabled" },
    });
  });
}
