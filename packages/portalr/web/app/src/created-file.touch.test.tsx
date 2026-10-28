/**
 * A native file the agent created blank, on a phone (portalr ADR-0055): the created card, and its
 * link to the change waiting for review, which focuses that proposal.
 */

import { afterEach, expect, test, vi } from "vitest";
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

async function serve(request: Request, path: string) {
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
