/**
 * A workspace, notes, as the small-screen tests see it: a thread whose run asked a question, a
 * note with a table, and titles and arguments longer than a phone is wide.
 */

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
export const serve = async (request: Request, path: string) => {
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

/** The world the routes open in: the log, and the note the run created. */
export const WORLD = {
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
};
