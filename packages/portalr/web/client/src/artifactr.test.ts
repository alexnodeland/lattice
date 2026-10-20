import { expect, test } from "vitest";
import { apply, artifactr, type Workspace } from "./artifactr";
import type * as v1 from "./generated/artifactr.v1";

function envelope(event: Record<string, unknown>, seq: number): v1.EventFrame {
  return {
    type: "event",
    seq,
    id: `evt_${seq}`,
    ts: "2026-10-12T00:00:00Z",
    workspace_id: "ws_1",
    actor: { kind: "user", id: "alice" },
    event: event as v1.Event,
  } as v1.EventFrame;
}

function replay(...events: Record<string, unknown>[]): Workspace {
  return events
    .map((event, index) => envelope(event, index + 1))
    .reduce(apply, artifactr.initial());
}

const live = (run: string, delta: string): v1.Server =>
  ({ type: "live", run_id: run, event: { type: "text_delta", part: 0, delta } }) as v1.Server;

test("a thread holds its title, mode, focus and messages", () => {
  const state = replay(
    { type: "thread_created", thread_id: "thr_1", title: "Launch" },
    { type: "thread_mode_changed", thread_id: "thr_1", mode: "suggest" },
    { type: "focus_changed", thread_id: "thr_1", artifact_ids: ["plan_1"] },
    { type: "message_posted", thread_id: "thr_1", message_id: "msg_1", content: "Hello" },
    {
      type: "message_posted",
      thread_id: "thr_1",
      message_id: "msg_2",
      content: "FYI",
      kind: "notice",
    },
  );
  expect(state.threads.thr_1).toEqual({
    id: "thr_1",
    title: "Launch",
    mode: "suggest",
    focus: ["plan_1"],
    messages: [
      {
        id: "msg_1",
        seq: 4,
        actor: { kind: "user", id: "alice" },
        content: "Hello",
        kind: "message",
        runId: null,
        feedback: [],
      },
      {
        id: "msg_2",
        seq: 5,
        actor: { kind: "user", id: "alice" },
        content: "FYI",
        kind: "notice",
        runId: null,
        feedback: [],
      },
    ],
    active: 5,
  });
});

test("a run streams its text until its message is posted, and keeps its status", () => {
  let state = replay(
    { type: "run_started", run_id: "run_1", thread_id: "thr_1" },
    {
      type: "tool_called",
      run_id: "run_1",
      thread_id: "thr_1",
      tool_call_id: "t1",
      tool_name: "edit",
    },
  );
  state = artifactr.other?.(state, live("run_1", "Draft")) ?? state;
  state = artifactr.other?.(state, live("run_1", "ing")) ?? state;
  expect(state.runs.run_1?.text).toBe("Drafting");
  state = [
    {
      type: "tool_returned",
      run_id: "run_1",
      thread_id: "thr_1",
      tool_call_id: "t1",
      tool_name: "edit",
      status: "ok",
    },
    {
      type: "message_posted",
      thread_id: "thr_1",
      message_id: "msg_9",
      content: "Drafting done",
      run_id: "run_1",
    },
    { type: "run_ended", run_id: "run_1", thread_id: "thr_1", status: "completed" },
  ]
    .map((event, index) => envelope(event, 3 + index))
    .reduce(apply, state);
  expect(state.runs.run_1).toEqual({
    id: "run_1",
    threadId: "thr_1",
    status: "completed",
    tools: { t1: { name: "edit", status: "ok", args: "", result: "", seq: 2 } },
    text: "",
    requests: [],
    answered: [],
    started: 1,
    ended: 5,
    error: null,
    reason: null,
    questions: [],
    feedback: [],
  });
});

test("a tool call keeps its arguments, what it returned and where it was called", () => {
  const state = replay(
    { type: "run_started", run_id: "run_1", thread_id: "thr_1" },
    {
      type: "tool_called",
      run_id: "run_1",
      thread_id: "thr_1",
      tool_call_id: "t1",
      tool_name: "draft_rule",
      args_summary: '{"rule": {}}',
    },
    {
      type: "tool_returned",
      run_id: "run_1",
      thread_id: "thr_1",
      tool_call_id: "t1",
      status: "retry",
      summary: "rule: Field required",
    },
    // Refused before it was called: its return is all there is, where it was returned.
    {
      type: "tool_returned",
      run_id: "run_1",
      thread_id: "thr_1",
      tool_call_id: "t2",
      tool_name: "draft_rule",
      status: "error",
      summary: "Boom",
    },
  );
  expect(state.runs.run_1?.tools).toEqual({
    t1: {
      name: "draft_rule",
      status: "retry",
      args: '{"rule": {}}',
      result: "rule: Field required",
      seq: 2,
    },
    t2: { name: "draft_rule", status: "error", args: "", result: "Boom", seq: 4 },
  });
});

test("a failed run keeps why, and when it ended", () => {
  const state = replay(
    { type: "run_started", run_id: "run_1", thread_id: "thr_1" },
    {
      type: "run_ended",
      run_id: "run_1",
      thread_id: "thr_1",
      status: "failed",
      error: "Tool 'draft_rule' exceeded max retries count of 1",
      reason: "unexpected_model_behavior",
    },
  );
  expect(state.runs.run_1).toMatchObject({
    status: "failed",
    ended: 2,
    error: "Tool 'draft_rule' exceeded max retries count of 1",
    reason: "unexpected_model_behavior",
  });
});

test("what a run asks through ask_user stays, with its answer, after the run ends", () => {
  const ask = {
    kind: "question",
    tool_call_id: "q1",
    tool_name: "ask_user",
    args: { questions: [] },
  };
  const approve = { kind: "approval", tool_call_id: "t2", tool_name: "publish", args: {} };
  const chosen = { answers: [{ selected: ["Monday"] }] };
  const state = replay(
    { type: "run_started", run_id: "run_1", thread_id: "thr_1" },
    { type: "run_paused", run_id: "run_1", thread_id: "thr_1", requests: [ask, approve] },
    {
      type: "deferred_answered",
      run_id: "run_1",
      thread_id: "thr_1",
      tool_call_id: "q1",
      answer: chosen,
    },
    // A second answer to it, refused by the server, would never be recorded; one is ignored.
    {
      type: "deferred_answered",
      run_id: "run_1",
      thread_id: "thr_1",
      tool_call_id: "q1",
      answer: { reply: "late" },
    },
    {
      type: "run_paused",
      run_id: "run_1",
      thread_id: "thr_1",
      requests: [{ ...ask, tool_call_id: "q2" }],
    },
    { type: "run_ended", run_id: "run_1", thread_id: "thr_1", status: "stopped" },
  );
  const alice = { kind: "user", id: "alice" };
  expect(state.runs.run_1?.questions).toEqual([
    { request: ask, seq: 2, answer: { value: chosen, actor: alice } },
    { request: { ...ask, tool_call_id: "q2" }, seq: 5, answer: null },
  ]);
});

test("a run pauses on its requests, and resumes when every one is answered", () => {
  const ask = { kind: "question", tool_call_id: "t1", tool_name: "ask", args: { q: "Which?" } };
  const approve = { kind: "approval", tool_call_id: "t2", tool_name: "edit_artifact", args: {} };
  const paused = replay(
    { type: "run_started", run_id: "run_2", thread_id: "thr_1" },
    { type: "run_paused", run_id: "run_2", thread_id: "thr_1", requests: [ask, approve] },
  );
  expect(paused.runs.run_2).toMatchObject({ status: "paused", requests: [ask, approve] });
  const answered = (state: Workspace, tool: string, seq: number) =>
    apply(
      state,
      envelope(
        { type: "deferred_answered", run_id: "run_2", thread_id: "thr_1", tool_call_id: tool },
        seq,
      ),
    );
  const half = answered(paused, "t2", 3);
  const alice = { kind: "user", id: "alice" };
  expect(half.runs.run_2).toMatchObject({
    status: "paused",
    requests: [ask],
    answered: [{ request: approve, actor: alice }],
  });
  const whole = answered(half, "t1", 4);
  expect(whole.runs.run_2).toMatchObject({
    status: "running",
    requests: [],
    answered: [
      { request: approve, actor: alice },
      { request: ask, actor: alice },
    ],
  });
  // Paused again, it waits on what it asks now, and what was answered before is put away.
  const again = apply(
    whole,
    envelope({ type: "run_paused", run_id: "run_2", thread_id: "thr_1", requests: [ask] }, 5),
  );
  expect(again.runs.run_2).toMatchObject({ status: "paused", requests: [ask], answered: [] });
});

test("a run that started before what the store read is left alone", () => {
  const state = replay({
    type: "run_ended",
    run_id: "run_0",
    thread_id: "thr_1",
    status: "failed",
  });
  expect(state.runs).toEqual({});
  expect(artifactr.other?.(state, live("run_0", "late"))).toBe(state);
});

test("artifacts keep their kind, latest version, whether they are archived, and where they were made", () => {
  const state = replay(
    {
      type: "artifact_created",
      artifact_id: "plan_1",
      kind: "plan",
      version: 1,
      data: {},
      thread_id: "thr_1",
    },
    {
      type: "artifact_changed",
      artifact_id: "plan_1",
      kind: "plan",
      version: 2,
      patch: { kind: "json_patch", ops: [] },
      summary: "",
      thread_id: "thr_2",
    },
    { type: "artifact_archived", artifact_id: "plan_1", kind: "plan", version: 3 },
  );
  expect(state.artifacts.plan_1).toEqual({
    id: "plan_1",
    kind: "plan",
    version: 3,
    archived: true,
    threadId: "thr_1",
    seq: 1,
    feedback: [],
  });
});

test("a proposal is open until it is accepted or rejected", () => {
  const change = { type: "create_artifact", artifact_id: "plan_2", kind: "plan", data: {} };
  const open = replay({
    type: "proposal_created",
    proposal_id: "prop_1",
    thread_id: "thr_1",
    run_id: "run_1",
    change,
    rationale: "A plan to start from.",
  });
  const proposal = {
    id: "prop_1",
    threadId: "thr_1",
    runId: "run_1",
    change,
    rationale: "A plan to start from.",
  };
  expect(open.proposals.prop_1).toEqual({ ...proposal, status: "open" });
  const resolved = apply(
    open,
    envelope(
      {
        type: "proposal_resolved",
        proposal_id: "prop_1",
        decision: "accept",
        proposed_by: null,
        artifact_id: "plan_1",
      },
      2,
    ),
  );
  expect(resolved.proposals.prop_1).toEqual({ ...proposal, status: "accept" });
  // One resolved before what the store read keeps what the resolution says.
  const late = apply(
    artifactr.initial(),
    envelope({ type: "proposal_resolved", proposal_id: "prop_9", decision: "reject" }, 1),
  );
  expect(late.proposals.prop_9).toEqual({
    id: "prop_9",
    threadId: null,
    runId: null,
    change: null,
    rationale: null,
    status: "reject",
  });
});

test("feedback on a message is kept with it, oldest first", () => {
  const thumbs = (up: boolean) => ({
    type: "feedback_given",
    feedback_type: "thumbs",
    target: { kind: "message", thread_id: "thr_1", message_id: "msg_1" },
    value: { up },
  });
  const state = replay(
    { type: "message_posted", thread_id: "thr_1", message_id: "msg_1", content: "Done." },
    { type: "message_posted", thread_id: "thr_1", message_id: "msg_2", content: "And this." },
    thumbs(true),
    thumbs(false),
  );
  const [first, second] = state.threads.thr_1?.messages ?? [];
  expect(first?.feedback).toEqual([
    { actor: { kind: "user", id: "alice" }, type: "thumbs", value: { up: true } },
    { actor: { kind: "user", id: "alice" }, type: "thumbs", value: { up: false } },
  ]);
  expect(second?.feedback).toEqual([]);
});

test("feedback on anything but a message, the application's events and unknown events change nothing", () => {
  const state = artifactr.initial();
  for (const event of [
    {
      type: "feedback_given",
      feedback_type: "thumbs",
      target: { kind: "thread", thread_id: "thr_1" },
      value: {},
    },
    { type: "app_event", name: "deployed" },
    { type: "something_new", detail: 1 },
  ]) {
    expect(apply(state, envelope(event, 1))).toBe(state);
  }
});

test("only a create with an id the client chose counts as a create", () => {
  expect(artifactr.creates({ type: "create_thread", thread_id: "thr_1", title: "x" })).toBe(true);
  expect(artifactr.creates({ type: "create_thread", title: "x" })).toBe(false);
  expect(
    artifactr.creates({ type: "post_message", thread_id: "thr_1", content: "x", message_id: "m" }),
  ).toBe(true);
  expect(artifactr.creates({ type: "stop_run", run_id: "run_1" })).toBe(false);
});

test("a run that ends waits on nothing more, and an answer to a running run doesn't resume it", () => {
  const ask = { kind: "question", tool_call_id: "t1", tool_name: "ask_user", args: {} };
  const paused = replay(
    { type: "run_started", run_id: "run_3", thread_id: "thr_1" },
    { type: "run_paused", run_id: "run_3", thread_id: "thr_1", requests: [ask] },
  );
  const ended = apply(
    paused,
    envelope({ type: "run_ended", run_id: "run_3", thread_id: "thr_1", status: "stopped" }, 3),
  );
  expect(ended.runs.run_3).toMatchObject({ status: "stopped", requests: [], answered: [] });
  const running = replay({ type: "run_started", run_id: "run_4", thread_id: "thr_1" });
  const late = apply(
    running,
    envelope(
      { type: "deferred_answered", run_id: "run_4", thread_id: "thr_1", tool_call_id: "t9" },
      2,
    ),
  );
  expect(late.runs.run_4).toMatchObject({ status: "running", answered: [] });
  const after = apply(
    ended,
    envelope(
      { type: "deferred_answered", run_id: "run_3", thread_id: "thr_1", tool_call_id: "t1" },
      4,
    ),
  );
  expect(after.runs.run_3?.status).toBe("stopped");
});

test("feedback on a message the store hasn't read has nowhere to go", () => {
  const state = replay({
    type: "message_posted",
    thread_id: "thr_1",
    message_id: "msg_1",
    content: "Hi",
  });
  for (const target of [
    { kind: "message", thread_id: "thr_9", message_id: "msg_1" },
    { kind: "message", thread_id: "thr_1", message_id: "msg_9" },
  ]) {
    const feedback = {
      type: "feedback_given",
      feedback_type: "thumbs",
      target,
      value: { up: true },
    };
    expect(apply(state, envelope(feedback, 2))).toBe(state);
  }
});

test("feedback on an artifact's version, and on a turn, is kept with it", () => {
  const thumbs = (target: Record<string, unknown>) => ({
    type: "feedback_given",
    feedback_type: "thumbs",
    target,
    value: { up: true, comment: "Clear" },
  });
  const state = replay(
    { type: "artifact_created", artifact_id: "plan_1", kind: "plan", version: 1 },
    { type: "run_started", run_id: "run_1", thread_id: "thr_1" },
    thumbs({ kind: "artifact", artifact_id: "plan_1", version: 1 }),
    thumbs({ kind: "turn", run_id: "run_1" }),
    thumbs({ kind: "artifact", artifact_id: "plan_9", version: 1 }),
    thumbs({ kind: "turn", run_id: "run_9" }),
  );
  const given = {
    actor: { kind: "user", id: "alice" },
    type: "thumbs",
    value: { up: true, comment: "Clear" },
  };
  expect(state.artifacts.plan_1?.feedback).toEqual([{ ...given, version: 1 }]);
  expect(state.runs.run_1?.feedback).toEqual([given]);
  expect(state.artifacts.plan_9).toBeUndefined();
  expect(state.runs.run_9).toBeUndefined();
});

test("each version of an artifact is judged anew: v1's thumbs aren't v3's", () => {
  const thumbs = (version: number) => ({
    type: "feedback_given",
    feedback_type: "thumbs",
    target: { kind: "artifact", artifact_id: "plan_1", version },
    value: { up: true },
  });
  const state = replay(
    { type: "artifact_created", artifact_id: "plan_1", kind: "plan", version: 1 },
    thumbs(1),
    { type: "artifact_changed", artifact_id: "plan_1", kind: "plan", version: 2 },
    { type: "artifact_changed", artifact_id: "plan_1", kind: "plan", version: 3 },
    thumbs(1), // late, for a version that has passed
  );
  expect(state.artifacts.plan_1).toMatchObject({ version: 3, feedback: [] });
  const judged = apply(state, envelope(thumbs(3), 6));
  expect(judged.artifacts.plan_1?.feedback).toHaveLength(1);
});
