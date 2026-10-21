/**
 * The offer of a new version, pinned by screenshots (portalr ADR-0058): wide and narrow, in both
 * schemes.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { NewVersion } from "./new-version";
import { dark } from "./test/colours";

for (const [name, width] of [
  ["wide", 900],
  ["narrow", 390],
] as const) {
  test(`a new version offered, ${name}`, async () => {
    await page.viewport(width, 300);
    onTestFinished(() => page.viewport(414, 896));
    const screen = await render(
      <div className="h-40 bg-paper">
        <NewVersion build="b" onReload={() => {}} onDismiss={() => {}} />
      </div>,
    );
    await document.fonts.ready;
    await commands.pointerAway();
    await expect(screen.getByRole("status", { name: "A new version" })).toMatchScreenshot(
      `new-version-${name}-${dark ? "dark" : "light"}`,
      { screenshotOptions: { animations: "disabled" } },
    );
  });
}
