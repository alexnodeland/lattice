/**
 * A native file's proposals, pinned by screenshots (portalr ADR-0050): one outdated, whose Accept
 * is disabled with the reason beside it, and a check-in's pages beside the head's, the same,
 * changed and new, wide and narrow, in each scheme, in colour-blind mode, and under forced
 * colours. Like the gallery's, the baselines are Linux's, made in CI.
 */

import type { Artifactr } from "@portalr/client";
import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Alert } from "./alert";
import { ProposalCard } from "./chat";
import { PageCompare } from "./native-file";
import { dark } from "./test/colours";
import { PAGES } from "./test/native-file";

const [ONE, TWO] = PAGES as [{ page: number; src: string }, { page: number; src: string }];

const proposal = (id: string, summary: string): Artifactr.Proposal => ({
  id,
  threadId: null,
  runId: null,
  change: {
    type: "edit_artifact",
    artifact_id: "doc_1",
    base_version: 1,
    patch: { kind: "json_patch", ops: [] },
    summary,
  },
  rationale: null,
  status: "open",
});

const respond = async () => ({ outcome: "done" as const });

function Proposals() {
  return (
    <div data-testid="proposals" className="flex flex-col gap-4 bg-paper p-4 text-fg">
      <ProposalCard
        proposal={proposal("p_1", "Add a sign-off")}
        onRespond={respond}
        blocked="Outdated: it was made against a version of the file since replaced, so accepting it would fail. Reject it, and ask the agent again: it plans again from version 3."
      >
        <p className="text-sm">The agent's edit, by WordCraft's commands.</p>
      </ProposalCard>
      <ProposalCard proposal={proposal("p_2", "Checked in launch-brief.docx")} onRespond={respond}>
        <p className="text-sm">
          A check-in kept as a proposal: the file changed after it was checked out.
        </p>
        <Alert tone="warn" live={false}>
          bob@acme.test has the file checked out.
        </Alert>
        <PageCompare
          label="Its pages beside the head's"
          before="Version 3"
          after="Proposed"
          pages={[
            { page: 1, before: ONE, after: ONE },
            { page: 2, before: ONE, after: TWO },
            { page: 3, before: null, after: { page: 3, state: "failed" } },
          ]}
        />
      </ProposalCard>
    </div>
  );
}

/** The proposals laid out at a width, with the faces loaded, in a mode if one is given. */
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
  await render(<Proposals />);
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  await document.fonts.ready;
  await commands.pointerAway();
}

async function matches(name: string) {
  await expect(page.getByTestId("proposals")).toMatchScreenshot(
    `${name}-${dark ? "dark" : "light"}`,
    { screenshotOptions: { animations: "disabled" } },
  );
}

test("a native file's proposals, wide", async () => {
  await shown(900);
  await matches("native-proposals-wide");
});

test("a native file's proposals, narrow", async () => {
  await shown(390);
  await matches("native-proposals-narrow");
});

test("a native file's proposals, in colour-blind mode", async () => {
  await shown(900, "colour-blind");
  await matches("native-proposals-colour-blind");
});

test("a native file's proposals, under forced colours", async () => {
  await shown(900, "forced-colours");
  await matches("native-proposals-forced-colours");
});
