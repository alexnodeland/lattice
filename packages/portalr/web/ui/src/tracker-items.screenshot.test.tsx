/**
 * The links to a tracker's items, pinned by screenshots (lattice RFC-0004): linked items in two
 * trackers, a deleted one, and names without an address, wide and narrow, in each scheme, in
 * colour-blind mode, and under forced colours. Like the gallery's, the baselines are Linux's, made
 * in CI.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { dark } from "./test/colours";
import { FILED, UNLINKED } from "./test/tracker-items";
import { TrackerItems } from "./tracker-items";

function Links() {
  return (
    <div data-testid="tracker-items" className="flex flex-col gap-3 bg-paper p-4 text-fg">
      <TrackerItems label="Filed as" items={FILED} />
      <TrackerItems label="From" items={UNLINKED} />
    </div>
  );
}

/** The links laid out at a width, with the faces loaded, in a mode if one is given. */
async function shown(width: number, mode?: "colour-blind" | "forced-colours") {
  await page.viewport(width, 600);
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
  await render(<Links />);
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('1em "Fragment Mono"'),
  ]);
  await document.fonts.ready;
  await commands.pointerAway();
}

async function matches(name: string) {
  await expect(page.getByTestId("tracker-items")).toMatchScreenshot(
    `${name}-${dark ? "dark" : "light"}`,
    { screenshotOptions: { animations: "disabled" } },
  );
}

test("the tracker's links, wide", async () => {
  await shown(900);
  await matches("tracker-items-wide");
});

test("the tracker's links, narrow", async () => {
  await shown(320);
  await matches("tracker-items-narrow");
});

test("the tracker's links, in colour-blind mode", async () => {
  await shown(900, "colour-blind");
  await matches("tracker-items-colour-blind");
});

test("the tracker's links, under forced colours", async () => {
  await shown(900, "forced-colours");
  await matches("tracker-items-forced-colours");
});
