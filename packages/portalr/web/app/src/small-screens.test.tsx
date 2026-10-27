/**
 * The app's own routes on a phone and a tablet (portalr ADR-0082): at 320, 360, 390, 430 and 768
 * nothing is wider than the page; what would be scrolls inside its own box.
 */

import { afterEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open } from "./test/app";

const FLAGS = "/grantr/v1/tenants/acme/workspaces/notes/enabled-integrations";
const at = (seq: number, actor: unknown, event: unknown) => ({
  type: "event",
  seq,
  id: `evt_${seq}`,
  ts: "2026-10-20T00:00:00Z",
  workspace_id: "notes",
  actor,
  event,
});
const alice = { kind: "user", id: "alice" };
const agent = (run: string) => ({ kind: "agent", id: "agent", run_id: run });
const LOG = [
  at(1, alice, {
    type: "thread_created",
    thread_id: "thr_1",
    title: "A launch plan whose title runs on past the width of any phone there is",
  }),
  at(2, alice, {
    type: "message_posted",
    thread_id: "thr_1",
    message_id: "m1",
    content: `Draft the launch note ${"x".repeat(90)} and pull the numbers from the sheet.`,
  }),
  at(3, agent("run_1"), { type: "run_started", run_id: "run_1", thread_id: "thr_1" }),
  at(4, agent("run_1"), {
    type: "tool_called",
    run_id: "run_1",
    thread_id: "thr_1",
    tool_call_id: "t1",
    tool_name: "list_artifacts",
    args_summary: `{"kind": "sheet", "q": "${"Q".repeat(80)}"}`,
  }),
  at(5, agent("run_1"), {
    type: "tool_returned",
    run_id: "run_1",
    thread_id: "thr_1",
    tool_call_id: "t1",
    tool_name: "list_artifacts",
    status: "ok",
    summary: "2 sheets",
  }),
  at(6, agent("run_1"), {
    type: "tool_called",
    run_id: "run_1",
    thread_id: "thr_1",
    tool_call_id: "t2",
    tool_name: "read_artifact",
    args_summary: '{"id": "art_q3"}',
  }),
  at(7, agent("run_1"), {
    type: "tool_returned",
    run_id: "run_1",
    thread_id: "thr_1",
    tool_call_id: "t2",
    tool_name: "read_artifact",
    status: "ok",
    summary: "28 rows",
  }),
  at(8, agent("run_1"), {
    type: "message_posted",
    thread_id: "thr_1",
    message_id: "m2",
    content:
      "I can draft it.\n\n```ts\nconst aVeryLongIdentifierNameThatGoesOnAndOn = readTheWholeSheetAndSummariseEveryColumn(1);\n```",
    run_id: "run_1",
  }),
  at(9, agent("run_1"), {
    type: "run_paused",
    run_id: "run_1",
    thread_id: "thr_1",
    requests: [
      {
        kind: "question",
        tool_call_id: "q1",
        tool_name: "ask_user",
        args: {
          questions: [
            {
              header: "Week",
              question: "Which week should the note cover?",
              options: [
                { label: "This week", description: "The current week", recommended: true },
                { label: "Next week", description: "The following week" },
              ],
            },
          ],
        },
      },
    ],
  }),
];
const serve = async (request: Request, path: string) => {
  if (path === "/grantr/v1/checks")
    return Response.json(((await request.json()) as unknown[]).map(() => true));
  if (path === FLAGS) return Response.json({});
  if (path === "/artifactr/v1/workspaces/notes/artifacts/note_1/revisions")
    return Response.json([
      {
        artifact_id: "note_1",
        version: 2,
        kind: "note",
        data: {
          text: `# Launch note\n\nShip on **Friday**. ${"word ".repeat(60)}\n\n| a | b | c | d | e | f |\n|---|---|---|---|---|---|\n| 1,204 | 1,390 | 1,612 | 8,310 | 9,944 | 12,207 |`,
        },
        archived: false,
        actor: { kind: "agent", thread_id: "thr_1", run_id: "run_1" },
      },
    ]);
  return path.startsWith("/grantr/v1/tenants/acme/") ? Response.json([]) : undefined;
};
afterEach(() => vi.unstubAllGlobals());

/** What scrolls inside its own box may be wider than the page; the page itself never is. */
function wider(): string[] {
  const scrolls = (element: Element | null): boolean =>
    element !== null &&
    element !== document.body &&
    (/auto|scroll/.test(getComputedStyle(element).overflowX) || scrolls(element.parentElement));
  return Array.from(document.body.querySelectorAll<HTMLElement>("*"))
    .filter(
      (element) =>
        element.getBoundingClientRect().right > window.innerWidth + 1 &&
        !scrolls(element.parentElement),
    )
    .map(
      (element) => `${element.tagName.toLowerCase()}.${element.className.toString().slice(0, 60)}`,
    );
}

const WIDTHS = [320, 360, 390, 430, 768];
const ROUTES: [string, string, string[]][] = [
  ["the threads list", "/t/acme/w/notes", ["Waiting for you"]],
  [
    "a thread with a question",
    "/t/acme/w/notes/threads/thr_1",
    ["Which week should the note cover?"],
  ],
  ["an artifact", "/t/acme/w/notes/artifacts/note_1", ["Ship on"]],
];
for (const [what, path, seen] of ROUTES) {
  for (const width of WIDTHS) {
    test(`${what} at ${width}px is never wider than the page`, async () => {
      await page.viewport(width, 900);
      const { screen } = await open(path, serve, () => null, {
        artifactrLog: [
          ...LOG,
          at(10, agent("run_1"), {
            type: "artifact_created",
            artifact_id: "note_1",
            kind: "note",
            version: 2,
            thread_id: "thr_1",
            run_id: "run_1",
          }),
        ],
      });
      for (const words of seen) {
        await expect.element(screen.getByText(words, { exact: false }).first()).toBeVisible();
      }
      const found = wider();
      expect(found, found.join("\n")).toEqual([]);
      expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
    });
  }
}
