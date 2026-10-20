/**
 * Artifacts inline in their thread, pinned by screenshots (portalr ADR-0055): a note, a form, a
 * submission and a dashboard through their renderers, a Word document a page at a time, and a workbook's cells,
 * each in the entry's chrome, wide and narrow, in each scheme; and a note's full view. The
 * baselines are Linux's, made in CI, with the faces loaded.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { ArtifactContent, markdown, type Renderers } from "./artifacts";
import { Button } from "./button";
import { InlineArtifact, Messages } from "./chat";
import { PageViewer, SheetTable } from "./file-preview";
import { FileHolder } from "./native-file";
import { SegmentedFilter } from "./segmented-filter";
import { StatusBadge } from "./status-badge";
import { dark } from "./test/colours";
import { SUPPORT } from "./test/dashboards";
import { LEAVE, LEAVE_UI } from "./test/forms";
import { PAGES } from "./test/native-file";
import { type FormHost, FormHostContext, UI_RENDERERS } from "./ui-renderers";

const RENDERERS: Renderers = new Map([["note", markdown()], ...UI_RENDERERS]);

const NOTE = `## Launch plan

Ship the **brief** on Friday, then:

1. Book the room
2. Send the invites

\`\`\`ts
export const day = "Friday";
\`\`\``;

const HOST: FormHost = {
  principal: "user:alice",
  submit: async () => ({ outcome: "done" }),
  form: () => null,
};

const open = <a href="#page">Open its page</a>;

function Thread() {
  return (
    <div data-testid="thread" className="bg-paper p-4 text-fg">
      <Messages>
        <InlineArtifact name="Launch plan" kind="Note" open={open}>
          <ArtifactContent kind="note" data={{ text: NOTE }} renderers={RENDERERS} />
        </InlineArtifact>
        <InlineArtifact name="Request leave" kind="Form" open={open}>
          <FormHostContext value={HOST}>
            <ArtifactContent
              kind="form"
              data={{
                title: "Request leave",
                schema: LEAVE,
                ui: LEAVE_UI,
                submissions: "once",
                closed: false,
              }}
              shown={{ id: "form_leave", version: 1 }}
              renderers={RENDERERS}
            />
          </FormHostContext>
        </InlineArtifact>
        <InlineArtifact name="Answers to Request leave" kind="Submission" open={open}>
          <ArtifactContent
            kind="submission"
            data={{ form_id: "form_leave", version: 1, values: { days: 3, reason: "A wedding" } }}
            renderers={RENDERERS}
          />
        </InlineArtifact>
        <InlineArtifact name="Support this week" kind="Dashboard" open={open}>
          <ArtifactContent kind="dashboard" data={SUPPORT} renderers={RENDERERS} />
        </InlineArtifact>
        <InlineArtifact name="launch-brief.docx" kind="Word document" open={open}>
          <div className="flex flex-col gap-3">
            <p className="text-muted text-sm">48 kB · 4 pages · version 3</p>
            <PageViewer
              label="launch-brief.docx, version 3"
              shown={PAGES[0] ?? { page: 1, state: "reading" }}
              total={4}
              onPage={() => {}}
            />
            <div>
              <FileHolder holder={{ kind: "free" }} />
            </div>
          </div>
        </InlineArtifact>
        <InlineArtifact name="figures.xlsx" kind="Workbook" open={open}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <SegmentedFilter
              label="Show figures.xlsx as"
              segments={[
                { value: "cells", label: "Cells" },
                { value: "outline", label: "Outline" },
                { value: "text", label: "Text" },
              ]}
              value="cells"
              onValueChange={() => {}}
            />
            <Button size="sm" className="ms-auto">
              Edit in GridCraft
            </Button>
          </div>
          <SheetTable
            sheet={{
              name: "Costs",
              rows: [
                ["Item", "Quantity", "Cost", "Notes"],
                ["Paper", "12", "18.40", ""],
                ["Toner", "2", "96.00", "black only"],
                ["Folders", "40", "22.00", ""],
              ],
            }}
          />
        </InlineArtifact>
        <InlineArtifact name="budget.xlsx" kind="Workbook" open={open}>
          {/* Flipped to its editor, as it opens: the box the preview had, the frame not yet drawn. */}
          <div className="flex h-72 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge tone="working">Opening budget.xlsx in GridCraft</StatusBadge>
              <Button variant="secondary" size="sm" className="ms-auto">
                Back to preview
              </Button>
            </div>
            <div className="min-h-0 flex-1 rounded-md border border-edge bg-paper" />
          </div>
        </InlineArtifact>
      </Messages>
    </div>
  );
}

async function shown(width: number) {
  await page.viewport(width, 3600);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(<Thread />);
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
    document.fonts.load('1em "Fragment Mono"'),
  ]);
  await document.fonts.ready;
  await expect.element(screen.getByRole("img", { name: "Page 1 of 4" })).toBeVisible();
  // The dashboard's bar chart names its series once its labels are measured.
  await expect
    .poll(() => [...document.querySelectorAll("svg text")].some((t) => t.textContent === "Phone"))
    .toBe(true);
  await new Promise((settled) => requestAnimationFrame(() => requestAnimationFrame(settled)));
  await commands.pointerAway();
  return screen;
}

for (const [name, width] of [
  ["wide", 900],
  ["narrow", 390],
] as const) {
  test(`every kind inline in its thread, ${name}`, async () => {
    const screen = await shown(width);
    for (const [entry, file] of [
      ["Launch plan", "note"],
      ["Request leave", "form"],
      ["Answers to Request leave", "submission"],
      ["Support this week", "dashboard"],
      ["launch-brief.docx", "word-document"],
      ["figures.xlsx", "workbook"],
      ["budget.xlsx", "editor-opening"],
    ] as const) {
      await expect
        .soft(screen.getByRole("listitem", { name: entry }))
        .toMatchScreenshot(`inline-${file}-${name}-${dark ? "dark" : "light"}`, {
          screenshotOptions: { animations: "disabled" },
        });
    }
  });
}

test("a note in its full view", async () => {
  await page.viewport(900, 700);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await shown(900);
  await page.viewport(900, 700);
  await screen
    .getByRole("listitem", { name: "Launch plan" })
    .getByRole("button", { name: "Full view" })
    .click();
  const full = screen.getByRole("dialog", { name: "Launch plan" });
  await expect.element(full).toBeVisible();
  await commands.pointerAway();
  await expect(full).toMatchScreenshot(`inline-note-full-view-${dark ? "dark" : "light"}`, {
    screenshotOptions: { animations: "disabled" },
  });
});
