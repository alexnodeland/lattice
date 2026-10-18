/**
 * Checking a file in, pinned by screenshots (portalr ADR-0049): a file to choose or drop, as it
 * waits and disabled while one is sent, and the upload's progress, wide and narrow, in each scheme,
 * in colour-blind mode, and under forced colours. Like the gallery's, the baselines are Linux's,
 * made in CI.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { FileChooser } from "./file-chooser";
import { Progress } from "./progress";
import { dark } from "./test/colours";

function CheckIn() {
  return (
    <div data-testid="check-in" className="flex flex-col gap-4 bg-paper p-4 text-fg">
      <FileChooser
        label="The edited file"
        hint="The file you saved from WordCraft, up to 26 MB."
        accept=".docx"
        onFile={() => undefined}
      />
      <FileChooser
        label="The edited file"
        hint="While one is sent."
        onFile={() => undefined}
        disabled
      />
      <Progress label="Checking in launch-brief.docx" value={21} max={48} />
    </div>
  );
}

/** The check-in laid out at a width, with the faces loaded, in a mode if one is given. */
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
  await render(<CheckIn />);
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  await document.fonts.ready;
  await commands.pointerAway();
}

async function matches(name: string) {
  await expect(page.getByTestId("check-in")).toMatchScreenshot(
    `${name}-${dark ? "dark" : "light"}`,
    { screenshotOptions: { animations: "disabled" } },
  );
}

test("a check-in, wide", async () => {
  await shown(900);
  await matches("check-in-wide");
});

test("a check-in, narrow", async () => {
  await shown(390);
  await matches("check-in-narrow");
});

test("a check-in, in colour-blind mode", async () => {
  await shown(900, "colour-blind");
  await matches("check-in-colour-blind");
});

test("a check-in, under forced colours", async () => {
  await shown(900, "forced-colours");
  await matches("check-in-forced-colours");
});
