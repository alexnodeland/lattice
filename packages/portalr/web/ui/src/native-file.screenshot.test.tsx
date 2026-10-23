/**
 * A native file's look, pinned by screenshots (portalr ADR-0048): its manifest, every holder a
 * file can have, and its pages, shown, being read and failed, wide and narrow, in each scheme, in
 * colour-blind mode, and under forced colours. Like the gallery's, the baselines are Linux's, made
 * in CI.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Card } from "./card";
import { FileHolder, PageStrip } from "./file-pages";
import { nativeFile } from "./native-file";
import { dark } from "./test/colours";
import { FAILED, MANIFEST, NOW, PAGES, UNTIL } from "./test/native-file";

function NativeFile() {
  return (
    <div data-testid="native-file" className="flex flex-col gap-6 bg-paper p-4 text-fg">
      <Card>{nativeFile().render(MANIFEST)}</Card>
      <div className="flex flex-wrap gap-2">
        <FileHolder holder={{ kind: "free" }} />
        <FileHolder holder={{ kind: "you", until: UNTIL }} now={NOW} />
        <FileHolder holder={{ kind: "person", who: "bob@acme.test", until: UNTIL }} now={NOW} />
        <FileHolder holder={{ kind: "agent" }} />
      </div>
      <PageStrip label="Pages" pages={PAGES} total={4} onMore={() => undefined} />
      <PageStrip label="Pages of version 1" pages={FAILED} total={1} />
    </div>
  );
}

/** The file laid out at a width, with the faces loaded, in a mode if one is given. */
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
  await render(<NativeFile />);
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  await document.fonts.ready;
  await commands.pointerAway();
}

async function matches(name: string) {
  await expect(page.getByTestId("native-file")).toMatchScreenshot(
    `${name}-${dark ? "dark" : "light"}`,
    { screenshotOptions: { animations: "disabled" } },
  );
}

test("a native file, wide", async () => {
  await shown(900);
  await matches("native-file-wide");
});

test("a native file, narrow", async () => {
  await shown(390);
  await matches("native-file-narrow");
});

test("a native file, in colour-blind mode", async () => {
  await shown(900, "colour-blind");
  await matches("native-file-colour-blind");
});

test("a native file, under forced colours", async () => {
  await shown(900, "forced-colours");
  await matches("native-file-forced-colours");
});
