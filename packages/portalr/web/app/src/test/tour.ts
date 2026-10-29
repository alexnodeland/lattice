/**
 * A thread as a tour of the agent's tools leaves it, for the phone's tests: a run at work, its
 * calls of four kinds, a Word document it made blank, a proposal on it that was accepted and
 * another that waits; and the frames of a turn streaming, with the tokens it has used.
 */

import { deliver } from "./app";
import { AT, FLAGS } from "./files";

const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
export const ALICE = { kind: "user", id: "alice" };
const AGENT = { kind: "agent", id: "agent", run_id: "run_1" };
export const logged = (seq: number, event: Record<string, unknown>, actor: unknown = AGENT) => ({
  type: "event",
  seq,
  id: `evt_${seq}`,
  ts: "2026-10-20T09:00:00Z",
  workspace_id: "notes",
  actor,
  event,
});
const call = (seq: number, id: string, name: string, args: string) => [
  logged(seq, {
    type: "tool_called",
    run_id: "run_1",
    thread_id: "thr_1",
    tool_call_id: id,
    tool_name: name,
    args_summary: args,
  }),
  logged(seq + 1, {
    type: "tool_returned",
    run_id: "run_1",
    thread_id: "thr_1",
    tool_call_id: id,
    tool_name: name,
    status: "ok",
    summary: "ok",
  }),
];
const manifest = {
  name: "Demo Document.docx",
  content: { sha256: "a".repeat(64), size: 48_213, media_type: DOCX },
  fingerprint: "f".repeat(64),
  text: null,
  review: null,
  outline: "",
  pages: 1,
  provenance: { source: "blank" },
};
const proposal = (seq: number, id: string, summary: string) =>
  logged(seq, {
    type: "proposal_created",
    proposal_id: id,
    thread_id: "thr_1",
    run_id: "run_1",
    rationale: "The agent's edit, by WordCraft's commands.",
    change: {
      type: "edit_artifact",
      artifact_id: "new_1",
      base_version: 1,
      summary,
      patch: { kind: "json_patch", ops: [] },
    },
  });
export const TOUR = [
  logged(
    1,
    { type: "thread_created", thread_id: "thr_1", title: "Quick tour of what you can do" },
    ALICE,
  ),
  logged(
    2,
    {
      type: "message_posted",
      thread_id: "thr_1",
      message_id: "m1",
      content: "What tools do you have access to and what can you do?",
    },
    ALICE,
  ),
  logged(3, { type: "run_started", run_id: "run_1", thread_id: "thr_1" }),
  ...call(4, "t1", "find_commands", '{"query":"heading"}'),
  logged(6, {
    type: "message_posted",
    thread_id: "thr_1",
    message_id: "m2",
    content: "Happy to - quick tour of everything. First I'll create things in parallel.",
    run_id: "run_1",
  }),
  ...call(7, "t2", "create_artifact", '{"title":"Demo Document.docx"}'),
  ...call(9, "t3", "create_artifact", '{"title":"Another"}'),
  ...call(11, "t4", "archive_artifact", '{"id":"x"}'),
  ...call(13, "t5", "mystery_tool", "{}"),
  logged(15, {
    type: "artifact_created",
    artifact_id: "new_1",
    kind: "word_document",
    version: 1,
    data: manifest,
    thread_id: "thr_1",
    run_id: "run_1",
  }),
  proposal(16, "p1", "Add a demo heading and two paragraphs"),
  logged(
    17,
    { type: "proposal_resolved", proposal_id: "p1", artifact_id: "new_1", decision: "accept" },
    ALICE,
  ),
  proposal(18, "p2", "Add a closing line"),
];
export const serve = async (request: Request, path: string) => {
  if (path === "/grantr/v1/checks")
    return Response.json(((await request.json()) as unknown[]).map(() => true));
  if (path === FLAGS) return Response.json({ "files:wordcraft": true });
  if (/\/artifacts\/new_1\/revisions$/.test(path))
    return Response.json([
      {
        artifact_id: "new_1",
        version: 1,
        kind: "word_document",
        data: manifest,
        archived: false,
        actor: AGENT,
      },
    ]);
  if (path === `${AT}/files/new_1`)
    return Response.json({
      artifact_id: "new_1",
      version: 1,
      name: manifest.name,
      media_type: DOCX,
      size: 48213,
      outline: "",
      pages: 1,
      lease: null,
      talk: "save",
      enabled: true,
      limit: 26214400,
    });
  return path.startsWith("/grantr/v1/tenants/acme/") ? Response.json([]) : undefined;
};

/** The frames a running turn streams: its thinking, words before a tool call, and its tokens. */
export function stream() {
  const live = (event: Record<string, unknown>) =>
    deliver({ type: "live", run_id: "run_1", event });
  live({ type: "part_started", part: 0, part_kind: "thinking" });
  live({ type: "thinking_delta", part: 0, delta: "The person wants a tour." });
  live({ type: "part_ended", part: 0 });
  live({ type: "part_started", part: 1, part_kind: "text" });
  live({
    type: "text_delta",
    part: 1,
    delta: "Happy to - quick tour of everything. First I'll create things in parallel.",
  });
  live({ type: "part_started", part: 2, part_kind: "tool_call", tool_name: "create_artifact" });
  const used = {
    input_tokens: 32_369,
    output_tokens: 6925,
    reasoning_tokens: 4955,
    model: "default",
  };
  live({ type: "usage", step: 0, usage: used, total: { requests: 1, ...used }, exact: true });
}

/** The tour, its run paused on `requests`. */
export const pausedOn = (requests: unknown[]) => [
  ...TOUR,
  logged(19, { type: "run_paused", run_id: "run_1", thread_id: "thr_1", requests }),
];

/** A run waiting on a question, after the tour. */
export const ASKING = pausedOn([
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
]);
