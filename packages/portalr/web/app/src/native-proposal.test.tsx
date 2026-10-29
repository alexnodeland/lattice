/**
 * A native file's proposals on the workspace's proposals, over a stubbed server and a stream that
 * replays them (portalr ADR-0050, ADR-0089): what each does in words, how each was made, one
 * outdated that can't be accepted, who has the file, and a proposal's words and pages beside the
 * head's, read once asked for.
 */

import axe from "axe-core";
import { afterEach, expect, test, vi } from "vitest";
import { proposedOf } from "./native-proposal";
import { open } from "./test/app";
import { AT, FILE, PNG, REVISIONS, status } from "./test/files";

const BLOB = { size: 48_300, media_type: "application/vnd.openxmlformats" };

/**
 * A proposal on `doc_1` as `revise` builds one, the log's `seq`th event: tested against `tested`,
 * made by `source`.
 */
const proposal = (seq: number, id: string, tested: string, source: string, summary: string) => ({
  type: "event",
  seq,
  id: `evt_${id}`,
  ts: "2026-10-17T09:30:00Z",
  workspace_id: "notes",
  actor: { kind: "user", id: "alice" },
  event: {
    type: "proposal_created",
    proposal_id: id,
    rationale: null,
    change: {
      type: "edit_artifact",
      artifact_id: "doc_1",
      base_version: 2,
      summary,
      patch: {
        kind: "json_patch",
        ops: [
          { op: "test", path: "/content/sha256", value: tested.repeat(64) },
          { op: "replace", path: "/content", value: { sha256: "c".repeat(64), ...BLOB } },
          { op: "replace", path: "/provenance", value: { source } },
          { op: "replace", path: "/pages", value: 3 },
        ],
      },
    },
  },
});

const CREATED = {
  type: "event",
  seq: 1,
  id: "evt_1",
  ts: "2026-10-17T09:00:00Z",
  workspace_id: "notes",
  actor: { kind: "user", id: "alice" },
  event: {
    type: "artifact_created",
    artifact_id: "doc_1",
    kind: "word_document",
    version: 2,
    data: {},
  },
};

const LOG = [
  CREATED,
  proposal(2, "p_now", "b", "commands", "Add a sign-off"),
  proposal(3, "p_old", "a", "commands", "Add a closing"),
  proposal(4, "p_in", "b", "check_in", "Checked in brief.docx"),
];

/** What the agent's edit at the head does, as the server says it from its commands. */
const SAID = {
  summary: "Types 22 characters and starts a new paragraph.",
  items: [
    { text: "Starts a new paragraph", name: "text.newParagraph", args: {} },
    {
      text: "Types “Signed off by the agent.”",
      name: "text.insert",
      args: { text: "Signed off by the agent." },
    },
  ],
  total: 3,
};

function serving(lease: unknown = null) {
  return async (_request: Request, path: string) => {
    switch (path) {
      case `${AT}/proposals/p_now/commands`:
        return Response.json(SAID);
      case `${AT}/artifacts/doc_1/revisions`:
        return Response.json(REVISIONS);
      case FILE:
        return Response.json(status(lease));
      case `${FILE}/versions/2/text`:
        return new Response("Brief\n\nFees");
      case `${AT}/proposals/p_in/text`:
        return new Response("Brief\n\nFees\n\nSigned");
      case `${FILE}/versions/2/pages/1`:
      case `${AT}/proposals/p_in/pages/1`:
      case `${AT}/proposals/p_in/pages/3`:
        return new Response(PNG);
      case `${FILE}/versions/2/pages/2`:
        return new Response(PNG.slice(0, 4));
      case `${AT}/proposals/p_in/pages/2`:
        return new Response(PNG.slice(0, 6));
      default:
        return undefined;
    }
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const card = (screen: Awaited<ReturnType<typeof open>>["screen"], summary: string) =>
  screen.getByRole("region", { name: `Proposal: ${summary}` });

test("an agent's edit at the head is accepted; one against a replaced version is outdated", async () => {
  const { screen } = await open(`/t/acme/w/notes/proposals`, serving(), undefined, {
    artifactrLog: LOG,
  });
  const now = card(screen, "Add a sign-off");
  await expect.element(now.getByText("The agent's edit, by WordCraft's commands.")).toBeVisible();
  await expect.element(now.getByRole("button", { name: "Accept" })).toBeEnabled();
  const old = card(screen, "Add a closing");
  await expect.element(old.getByText("Outdated", { exact: true })).toBeVisible();
  const accept = old.getByRole("button", { name: "Accept" });
  await expect.element(accept).toBeDisabled();
  await expect.element(accept).toHaveAccessibleDescription(/^Outdated: it was made against/);
  await expect.element(old.getByRole("button", { name: "Reject" })).toBeEnabled();
});

test("an agent's edit says what it does, then each change, its arguments and its commands", async () => {
  const { screen } = await open(`/t/acme/w/notes/proposals`, serving(), undefined, {
    artifactrLog: LOG,
  });
  const now = card(screen, "Add a sign-off");
  const line = now.getByRole("button", { name: SAID.summary });
  await expect.element(line).toHaveAttribute("aria-expanded", "false");
  await line.click();
  await expect.element(line).toHaveAttribute("aria-expanded", "true");
  const changes = now.getByRole("list", { name: "Its changes" });
  await expect.element(changes).toBeVisible();
  expect(changes.getByRole("listitem").elements()).toHaveLength(2);
  await expect.element(now.getByText("And 1 more.")).toBeVisible();
  await changes.getByRole("button", { name: "Types “Signed off by the agent.”" }).click();
  await expect.element(changes.getByText('"Signed off by the agent."')).toBeVisible();
  await now.getByRole("button", { name: /^Its commands/ }).click();
  await expect.element(now.getByText('"text.newParagraph"')).toBeVisible();
  const { violations } = await axe.run(now.element(), { resultTypes: ["violations"] });
  expect(violations.map((violation) => violation.id)).toEqual([]);
  // A read that failed says so; a check-in has no commands to say, and says nothing of them.
  await expect
    .element(card(screen, "Add a closing").getByText(/^Couldn't read what this does/))
    .toBeVisible();
  const checkedIn = card(screen, "Checked in brief.docx");
  await expect.element(checkedIn.getByText(/^A check-in kept as a proposal/)).toBeVisible();
  expect(checkedIn.getByRole("button", { name: /^Types/ }).elements()).toHaveLength(0);
});

test("a check-in kept as a proposal is compared with the head, words and pages", async () => {
  const { screen, fetched } = await open(`/t/acme/w/notes/proposals`, serving(), undefined, {
    artifactrLog: LOG,
  });
  const checkedIn = card(screen, "Checked in brief.docx");
  await expect.element(checkedIn.getByText(/^A check-in kept as a proposal/)).toBeVisible();
  const read = () =>
    fetched.mock.calls.filter(([input]) =>
      new URL((input as Request).url).pathname.startsWith(`${AT}/proposals/p_in/`),
    ).length;
  // A check-in has no commands to read; its words and pages are read only once asked for.
  expect(read()).toBe(0);
  await checkedIn.getByText("Compare with version 2 (proposed: 48 kB)").click();
  await expect
    .poll(() => checkedIn.element().querySelector("ins")?.textContent)
    .toContain("Signed");
  const pages = checkedIn.getByRole("region", { name: "Its pages beside the head's" });
  const rows = () => [...pages.element().querySelectorAll("li > p")].map((row) => row.textContent);
  await expect.poll(rows).toEqual(["Page 1Unchanged", "Page 2Changed", "Page 3New"]);
  await expect.element(pages.getByText("No page 3 here")).toBeVisible();
});

test("while someone has the file checked out, accepting is said to make theirs a proposal", async () => {
  const lease = { checked_out_by: "user:bob", expires_at: "2026-10-17T17:30:00Z" };
  const { screen } = await open(`/t/acme/w/notes/proposals`, serving(lease), undefined, {
    artifactrLog: LOG,
  });
  await expect
    .element(card(screen, "Add a sign-off").getByText(/has the file checked out: accepting this/))
    .toBeVisible();
});

test("an outdated check-in is to be made again from the head; one resolved reads nothing more", async () => {
  const resolved = {
    type: "event",
    seq: 6,
    id: "evt_6",
    ts: "2026-10-17T10:00:00Z",
    workspace_id: "notes",
    actor: { kind: "user", id: "alice" },
    event: {
      type: "proposal_resolved",
      proposal_id: "p_was",
      artifact_id: "doc_1",
      decision: "reject",
    },
  };
  const log = [
    CREATED,
    proposal(2, "p_late", "a", "check_in", "Checked in late"),
    proposal(3, "p_was", "b", "commands", "Add a footer"),
    resolved,
  ];
  const mine = { checked_out_by: "user:alice", expires_at: "2026-10-17T17:30:00Z" };
  const { screen } = await open(`/t/acme/w/notes/proposals`, serving(mine), undefined, {
    artifactrLog: log,
  });
  const late = card(screen, "Checked in late");
  await expect
    .element(late.getByRole("button", { name: "Accept" }))
    .toHaveAccessibleDescription(/check the file out again from version 2, and make the change/);
  await expect.element(late.getByText(/^You have the file checked out/)).toBeVisible();
  const was = card(screen, "Add a footer");
  await expect.element(was.getByText("Rejected")).toBeVisible();
  await expect.element(was.getByText("The agent's edit, by WordCraft's commands.")).toBeVisible();
  expect(was.getByText(/^Compare with/).elements()).toHaveLength(0);
  expect(was.getByText(/checked out/).elements()).toHaveLength(0);
});

test("a proposal's patch says what it was made from, how, and its pages", () => {
  const [, made] = LOG as [unknown, { event: { change: never } }];
  expect(proposedOf(made.event.change)).toEqual({
    tested: "b".repeat(64),
    source: "commands",
    pages: 3,
    size: 48_300,
  });
  expect(proposedOf(null)).toBeNull();
  expect(
    proposedOf({
      type: "edit_artifact",
      artifact_id: "doc_1",
      base_version: 1,
      patch: { kind: "json_patch", ops: [{ op: "replace", path: "/name", value: "x" }] },
    }),
  ).toEqual({ tested: null, source: null, pages: null, size: null });
});
