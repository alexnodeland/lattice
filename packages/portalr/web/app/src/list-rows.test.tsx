/**
 * The workspace's lists say enough on their second line to tell rows apart (the polish pass):
 * a thread by who spoke last, what they said and when; an artifact by its kind, its version and
 * when it was made, never its raw id, which its own page holds.
 */

import { afterEach, expect, test, vi } from "vitest";
import { open } from "./test/app";
import { FLAGS } from "./test/files";

const ALICE = { kind: "user", id: "alice" };
const AGENT = { kind: "agent", thread_id: "thr_1", run_id: "run_1" };

const logged = (
  seq: number,
  ts: string,
  event: Record<string, unknown>,
  actor: unknown = ALICE,
) => ({
  type: "event",
  seq,
  id: `evt_${seq}`,
  ts,
  workspace_id: "notes",
  actor,
  event,
});

const minutes = (count: number) => new Date(Date.now() - count * 60_000).toISOString();

const LOG = [
  logged(1, minutes(90), { type: "thread_created", thread_id: "thr_1", title: "Lisbon offsite" }),
  logged(2, minutes(80), { type: "thread_created", thread_id: "thr_2", title: "Lisbon offsite" }),
  logged(3, minutes(70), {
    type: "message_posted",
    thread_id: "thr_1",
    message_id: "msg_1",
    content: "# Book the **flights**\n\nfor twelve",
  }),
  logged(
    4,
    minutes(5),
    {
      type: "message_posted",
      thread_id: "thr_2",
      message_id: "msg_2",
      content: "The dietary form is ready.",
      run_id: "run_1",
    },
    AGENT,
  ),
  logged(
    5,
    minutes(3),
    {
      type: "artifact_created",
      artifact_id: "art_0123456789abcdef",
      kind: "pdf_document",
      version: 2,
      data: {},
      thread_id: "thr_2",
    },
    AGENT,
  ),
];

function serving() {
  return async (request: Request, path: string) => {
    if (path === "/grantr/v1/checks") {
      return Response.json(((await request.json()) as unknown[]).map(() => true));
    }
    if (path === FLAGS) {
      return Response.json({});
    }
    if (path.endsWith("/workspaces/notes/artifacts")) {
      return Response.json([]);
    }
    return undefined;
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("threads of one title are told apart by who spoke last, what they said, and when", async () => {
  const { screen } = await open("/t/acme/w/notes", serving(), undefined, { artifactrLog: LOG });
  const rows = screen.getByRole("list", { name: "Threads" }).getByRole("listitem");
  await expect.poll(() => rows.first().element().textContent).toContain("Lisbon offsite");
  // The most recently active first.
  await expect
    .poll(() => rows.nth(0).element().textContent)
    .toContain("Assistant: The dietary form is ready. · 5 minutes ago");
  await expect
    .poll(() => rows.nth(1).element().textContent)
    .toContain("You: Book the flights · 1 hour ago");
  // Read with the link, as its description.
  await expect
    .element(rows.nth(1).getByRole("link", { name: "Lisbon offsite" }))
    .toHaveAccessibleDescription("You: Book the flights · 1 hour ago");
});

test("an artifact's row says its kind, its version and when, and not its raw id", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts", serving(), undefined, {
    artifactrLog: LOG,
  });
  const row = screen.getByRole("list", { name: "Artifacts" }).getByRole("listitem").first();
  await expect
    .poll(() => row.element().textContent)
    .toContain("PDF document · version 2 · 3 minutes ago");
  // Untitled, it is named by its id; its second line never repeats it.
  const meta = row.element().querySelector("[id$='-meta']");
  expect(meta?.textContent).not.toContain("art_");
});
