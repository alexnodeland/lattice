/**
 * Uploading files, pinned by screenshots (native files ADR-0017): files to choose or drop, several
 * at once, and the list of them, done, going, waiting and refused, wide and narrow, in each scheme,
 * in colour-blind mode, and under forced colours. Like the gallery's, the baselines are Linux's,
 * made in CI.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { FileChooser } from "./file-chooser";
import { dark } from "./test/colours";
import { UploadList } from "./upload-list";

function Uploading() {
  return (
    <div data-testid="upload" className="flex flex-col gap-4 bg-paper p-4 text-fg">
      <FileChooser
        label="Upload files"
        hint=".docx, .xlsx, .pdf, up to 26 MB each."
        multiple
        onFile={() => undefined}
      />
      <UploadList
        items={[
          {
            id: "1",
            name: "launch-brief.docx",
            size: 48_213,
            state: "done",
            said: "Uploaded launch-brief.docx.",
          },
          { id: "2", name: "budget.xlsx", size: 120_000, state: "sending", sent: 52_000 },
          { id: "3", name: "deck.pdf", size: 2_400_000, state: "waiting" },
          {
            id: "4",
            name: "scan.pdf",
            size: 3_100_000,
            state: "failed",
            tone: "error",
            again: true,
            said: "PdfCraft couldn't finish reading scan.pdf. Try again in a moment.",
          },
        ]}
        onStop={() => undefined}
        onRemove={() => undefined}
        onRetry={() => undefined}
      />
    </div>
  );
}

/** The uploads laid out at a width, with the faces loaded, in a mode if one is given. */
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
  await render(<Uploading />);
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  await document.fonts.ready;
  await commands.pointerAway();
}

async function matches(name: string) {
  await expect(page.getByTestId("upload")).toMatchScreenshot(`${name}-${dark ? "dark" : "light"}`, {
    screenshotOptions: { animations: "disabled" },
  });
}

test("uploads, wide", async () => {
  await shown(900);
  await matches("upload-wide");
});

test("uploads, narrow", async () => {
  await shown(390);
  await matches("upload-narrow");
});

test("uploads, in colour-blind mode", async () => {
  await shown(900, "colour-blind");
  await matches("upload-colour-blind");
});

test("uploads, under forced colours", async () => {
  await shown(900, "forced-colours");
  await matches("upload-forced-colours");
});
