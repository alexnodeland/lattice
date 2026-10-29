/**
 * A native file the agent created blank, on a phone (portalr ADR-0055): the created card, its link
 * to the change waiting for review, which focuses that proposal, and that proposal's changes, in
 * a sheet (portalr ADR-0089).
 */

import axe from "axe-core";
import { afterEach, expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { open } from "./test/app";

const AGENT = { kind: "agent", thread_id: "thr_1", run_id: "run_1" };
const ALICE = { kind: "user", id: "alice" };

const logged = (seq: number, event: Record<string, unknown>, actor: unknown = AGENT) => ({
  type: "event",
  seq,
  id: `evt_${seq}`,
  ts: "2026-10-28T09:00:00Z",
  workspace_id: "notes",
  actor,
  event,
});

const LOG = [
  logged(1, { type: "thread_created", thread_id: "thr_1", title: "Trip" }, ALICE),
  logged(
    2,
    { type: "message_posted", thread_id: "thr_1", message_id: "msg_1", content: "Plan it" },
    ALICE,
  ),
  logged(3, {
    type: "artifact_created",
    artifact_id: "new_1",
    kind: "presentation",
    version: 1,
    data: {},
    thread_id: "thr_1",
    run_id: "run_1",
  }),
  logged(4, {
    type: "proposal_created",
    proposal_id: "prop_1",
    thread_id: "thr_1",
    run_id: "run_1",
    rationale: null,
    change: {
      type: "edit_artifact",
      artifact_id: "new_1",
      base_version: 1,
      summary: "Write the slides",
      patch: { kind: "json_patch", ops: [] },
    },
  }),
];

const BLANK = {
  name: "Trip.pptx",
  content: {
    sha256: "a".repeat(64),
    size: 28_000,
    media_type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  },
  fingerprint: "f".repeat(64),
  text: null,
  review: null,
  outline: "",
  pages: 1,
  provenance: { source: "blank", app: "deckcraft" },
};

const SAID = {
  summary: "Adds 2 slides: Trip and Day 1.",
  items: [
    { text: "Adds a slide: “Trip”", name: "slide.new", args: { title: "Trip" } },
    { text: "Adds a slide: “Day 1”", name: "slide.new", args: { title: "Day 1", body: "Lisbon" } },
  ],
  total: 2,
};

async function serve(request: Request, path: string) {
  if (path.endsWith("/proposals/prop_1/commands")) {
    return Response.json(SAID);
  }
  if (path === "/grantr/v1/checks") {
    return Response.json(((await request.json()) as unknown[]).map(() => true));
  }
  if (path.endsWith("/artifacts/new_1/revisions")) {
    return Response.json([
      { artifact_id: "new_1", version: 1, kind: "presentation", data: BLANK, archived: false },
    ]);
  }
  return undefined;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("on a phone, a file created blank says so, and its link reaches the change waiting", async () => {
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, undefined, {
    artifactrLog: LOG,
  });
  const file = screen.getByRole("listitem", { name: "Trip.pptx" });
  await expect.element(file.getByText("Presentation", { exact: true })).toBeVisible();
  const waiting = file.getByRole("link", {
    name: "The agent's changes are waiting for your review.",
  });
  await waiting.click();
  await expect
    .element(screen.getByRole("region", { name: "Proposal: Write the slides" }))
    .toHaveFocus();
  expect(file.getByRole("radio").elements()).toHaveLength(0);
});

test("on a phone, a proposal's changes open in a sheet, each to its arguments and back", async () => {
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, undefined, {
    artifactrLog: LOG,
  });
  const line = screen.getByRole("button", { name: SAID.summary });
  await expect.element(line).toHaveAttribute("aria-haspopup", "dialog");
  await line.click();
  const sheet = screen.getByRole("dialog", { name: SAID.summary });
  const day = sheet.getByRole("button", { name: "Adds a slide: “Day 1”" });
  await expect.element(day).toBeVisible();
  const { violations } = await axe.run(sheet.element(), { resultTypes: ["violations"] });
  expect(violations.map((violation) => violation.id)).toEqual([]);
  await day.click();
  const back = sheet.getByRole("button", { name: "Back to the changes" });
  await expect.element(back).toHaveFocus();
  await expect.element(sheet.getByText('"Lisbon"')).toBeVisible();
  await back.click();
  await expect.element(day).toHaveFocus();
  // Escape from a change goes back to the list; from the list, it closes.
  await day.click();
  await expect.element(back).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  await expect.element(day).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  await expect.element(line).toHaveFocus();
  await line.click();
  await sheet.getByRole("button", { name: "Close" }).click();
  await expect.element(line).toHaveFocus();
});

test("a proposal on a native file is compared with the head from its thread", async () => {
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, undefined, {
    artifactrLog: LOG,
  });
  const proposal = screen.getByRole("region", { name: "Proposal: Write the slides" });
  await proposal.getByRole("button", { name: /^Compare with version 1/ }).click();
  await expect.element(proposal.getByText("Its words")).toBeVisible();
});
