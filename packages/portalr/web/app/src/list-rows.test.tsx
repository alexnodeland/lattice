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

const titled = (seq: number, ts: string) =>
  logged(seq, ts, {
    type: "artifact_created",
    artifact_id: "art_note",
    kind: "note",
    version: 1,
    data: {},
  });

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
      return Response.json([
        { id: "art_note", kind: "note", version: 1, data: { text: "# Flights on Monday" } },
      ]);
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
    .toHaveAccessibleDescription("You: Book the flights");
});

test("an artifact's row says its kind, its version and when, and not its raw id", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts", serving(), undefined, {
    artifactrLog: [...LOG, titled(6, minutes(30))],
  });
  const rows = screen.getByRole("list", { name: "Artifacts" }).getByRole("listitem");
  // The most recently made or changed first: the PDF, made 3 minutes ago, before the note.
  const titledRow = rows.nth(1);
  await expect.poll(() => titledRow.element().textContent).toContain("Flights on Monday");
  expect(titledRow.element().textContent).toContain("Note · version 1 · 30 minutes ago");
  expect(titledRow.element().textContent).not.toContain("art_note");
  // Its link goes to its page by its id, where the id is shown.
  expect(titledRow.getByRole("link").element().getAttribute("href")).toMatch(
    /\/artifacts\/art_note$/,
  );
  const row = rows.first();
  await expect
    .poll(() => row.element().textContent)
    .toContain("PDF document · version 2 · 3 minutes ago");
  // Untitled, it is named by its id; its second line never repeats it.
  const meta = row.element().querySelector("[id$='-meta']");
  expect(meta?.textContent).not.toContain("art_");
});

test("a row's second line holds up: right to left, emoji, long, empty, and a time ahead of the clock", async () => {
  const thread = (seq: number, id: string, title: string) =>
    logged(seq, minutes(60), { type: "thread_created", thread_id: id, title });
  const said = (seq: number, id: string, content: string, ts = minutes(2)) =>
    logged(seq, ts, { type: "message_posted", thread_id: id, message_id: `m${seq}`, content });
  const long = "Book ".repeat(200);
  const { screen } = await open("/t/acme/w/notes", serving(), undefined, {
    artifactrLog: [
      thread(1, "thr_a", "رحلة لشبونة"),
      said(2, "thr_a", "احجز الرحلات يوم الاثنين"),
      thread(3, "thr_b", "Emoji"),
      said(4, "thr_b", "🎉 Booked ✈️"),
      thread(5, "thr_c", "Long"),
      said(6, "thr_c", long),
      thread(7, "thr_d", "Empty"),
      said(8, "thr_d", "```\n\n```"),
      thread(9, "thr_e", ""),
      // A server clock a little fast: the time is never in the future.
      said(10, "thr_e", "Ahead", new Date(Date.now() + 5 * 60_000).toISOString()),
    ],
  });
  const row = (name: string) =>
    screen.getByRole("list", { name: "Threads" }).getByRole("listitem").filter({ hasText: name });
  await expect
    .poll(() => row("رحلة لشبونة").element().textContent)
    .toContain("You: احجز الرحلات يوم الاثنين");
  expect(row("Emoji").element().textContent).toContain("You: 🎉 Booked ✈️");
  // A long one is capped by its title's length, not clipped, and its time still shows.
  const longText = row("Long").element().textContent ?? "";
  expect(longText).toContain("…");
  expect(longText).toMatch(/minutes ago$/);
  // Nothing with words in it is said as an ellipsis.
  expect(row("Empty").element().textContent).toContain("You: …");
  // An untitled thread is named as such, and its time ahead of the clock is "now".
  expect(row("Untitled").element().textContent).toContain("You: Ahead · now");
});
