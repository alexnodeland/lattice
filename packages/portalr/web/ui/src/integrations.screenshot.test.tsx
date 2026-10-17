/**
 * The integrations list's look, pinned by screenshots (portalr ADR-0019, ADR-0045): every state a
 * switch can be in, on by default, inherited, set here, off by the tenant's ceiling, not
 * installed, and saving, wide and narrow, in each scheme, in colour-blind mode, and under forced
 * colours. Like the gallery's, the baselines are Linux's, made in CI.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { IntegrationList } from "./integration-list";
import { dark } from "./test/colours";
import { ROWS, SAVING } from "./test/integrations";

function Integrations() {
  return (
    <div data-testid="integrations" className="bg-paper p-4 text-fg">
      <IntegrationList
        caption="Integrations in notes"
        level="workspace"
        rows={ROWS}
        saving={SAVING}
        onSwitch={() => undefined}
        onInherit={() => undefined}
        history={() => <span className="text-accent text-xs underline">History</span>}
      />
    </div>
  );
}

/** The list laid out at a width, with the faces loaded, in a mode if one is given. */
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
  await render(<Integrations />);
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  await document.fonts.ready;
  await commands.pointerAway();
}

async function matches(name: string) {
  await expect(page.getByTestId("integrations")).toMatchScreenshot(
    `${name}-${dark ? "dark" : "light"}`,
    { screenshotOptions: { animations: "disabled" } },
  );
}

test("the integrations, wide", async () => {
  await shown(900);
  await matches("integrations-wide");
});

test("the integrations, narrow", async () => {
  await shown(390);
  await matches("integrations-narrow");
});

test("the integrations, in colour-blind mode", async () => {
  await shown(900, "colour-blind");
  await matches("integrations-colour-blind");
});

test("the integrations, under forced colours", async () => {
  await shown(900, "forced-colours");
  await matches("integrations-forced-colours");
});
