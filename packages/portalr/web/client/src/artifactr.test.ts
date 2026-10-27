import { expect, test } from "vitest";
import { apply, applyLive, applyWelcome, artifactr, CAP, type Workspace } from "./artifactr";
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
    activeAt: "2026-10-12T00:00:00Z",
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
    tools: {
      t1: {
        name: "edit",
        status: "ok",
        args: "",
        result: "",
        argsCut: false,
        resultCut: false,
        seq: 2,
      },
    },
    text: "",
    live: {
      phase: "starting",
      tool: null,
      calls: 0,
      argsChars: 0,
      thinking: "",
      thoughtMs: 0,
      outputChars: 8,
      since: expect.any(Number),
      at: expect.any(Number),
      part: null,
      reply: "posted",
      truncated: true, // its first frame wasn't a part's start
      framed: true,
    },
    requests: [],
    answered: [],
    started: 1,
    startedAt: "2026-10-12T00:00:00Z",
    ended: 5,
    error: null,
    reason: null,
    prompt: [],
    actsFor: null,
    questions: [],
    feedback: [],
  });
});

/** A live frame of `run`, as the server sends it. */
const frame = (run: string, event: Record<string, unknown>): v1.Server =>
  ({ type: "live", run_id: run, event }) as unknown as v1.Server;

const started = () => replay({ type: "run_started", run_id: "run_1", thread_id: "thr_1" });

/** The state after each frame, at a second apart, from `at`. */
function streamed(state: Workspace, frames: Record<string, unknown>[], at = 1000): Workspace {
  return frames.reduce(
    (next, event, index) => applyLive(next, frame("run_1", event), at + index * 1000),
    state,
  );
}

test("a run's thinking streams, its phase follows it, and its time is counted as it ends", () => {
  let state = started();
  expect(state.runs.run_1?.live.phase).toBe("starting");
  state = streamed(state, [
    { type: "part_started", part: 0, part_kind: "thinking" },
    { type: "thinking_delta", part: 0, delta: "Let me " },
    { type: "thinking_delta", part: 0, delta: "see." },
  ]);
  expect(state.runs.run_1?.live).toMatchObject({
    phase: "thinking",
    thinking: "Let me see.",
    since: 1000,
    at: 3000,
    outputChars: 11,
  });
  state = streamed(state, [{ type: "part_ended", part: 0 }], 13_000);
  expect(state.runs.run_1?.live).toMatchObject({ phase: "starting", thoughtMs: 12_000 });
  expect(state.runs.run_1?.text).toBe("");
});

test("a tool call is prepared as its arguments stream, runs once its call is on the log, and returns", () => {
  let state = streamed(started(), [
    { type: "part_started", part: 0, part_kind: "tool_call", tool_name: "create_app" },
    { type: "tool_args_delta", part: 0, delta: '{"html": "<!doctype' },
    { type: "tool_args_delta", part: 0, delta: ' html>"}' },
    { type: "part_ended", part: 0 },
  ]);
  expect(state.runs.run_1?.live).toMatchObject({
    phase: "tool",
    tool: "create_app",
    calls: 0,
    argsChars: 27,
    outputChars: 27,
    since: 1000,
    at: 4000,
  });
  const call = { run_id: "run_1", thread_id: "thr_1", tool_call_id: "t1", tool_name: "create_app" };
  state = apply(state, envelope({ type: "tool_called", ...call }, 2));
  expect(state.runs.run_1?.live).toMatchObject({
    phase: "tool",
    tool: "create_app",
    calls: 1,
  });
  state = apply(state, envelope({ type: "tool_returned", ...call, status: "ok" }, 3));
  expect(state.runs.run_1?.live).toMatchObject({ phase: "starting", tool: null, argsChars: 0 });
});

test("the text of a new response replaces what the model wrote before its tool call", () => {
  let state = streamed(started(), [
    { type: "part_started", part: 0, part_kind: "text" },
    { type: "text_delta", part: 0, delta: "I'll draft it." },
    { type: "part_ended", part: 0 },
    { type: "part_started", part: 1, part_kind: "tool_call", tool_name: "draft" },
    { type: "part_ended", part: 1 },
  ]);
  expect(state.runs.run_1?.text).toBe("I'll draft it.");
  // The next response's parts start over at 0: its text is the reply.
  state = streamed(state, [
    { type: "part_started", part: 0, part_kind: "text" },
    { type: "text_delta", part: 0, delta: "Here it is." },
  ]);
  expect(state.runs.run_1).toMatchObject({ text: "Here it is.", live: { phase: "writing" } });
  // Within one response, a second text part goes on from the first.
  state = streamed(state, [
    { type: "part_ended", part: 0 },
    { type: "part_started", part: 1, part_kind: "text" },
    { type: "text_delta", part: 1, delta: " Done." },
  ]);
  expect(state.runs.run_1?.text).toBe("Here it is. Done.");
  expect(state.runs.run_1?.live.outputChars).toBe("I'll draft it.Here it is. Done.".length);
});

test("a part of a kind this client doesn't know still counts as the last part", () => {
  let state = streamed(started(), [
    { type: "part_started", part: 0, part_kind: "text" },
    { type: "text_delta", part: 0, delta: "Before." },
    { type: "part_started", part: 1, part_kind: "image" },
  ]);
  expect(state.runs.run_1?.live.part).toBe(1);
  // A text part numbered after it goes on in the same response.
  state = streamed(state, [
    { type: "part_started", part: 2, part_kind: "text" },
    { type: "text_delta", part: 2, delta: " After." },
  ]);
  expect(state.runs.run_1?.text).toBe("Before. After.");
});

test("a welcome starts every running run's live output over, so a replay shows nothing twice", () => {
  const frames = [
    { type: "part_started", part: 0, part_kind: "thinking" },
    { type: "thinking_delta", part: 0, delta: "Hmm." },
    { type: "part_started", part: 1, part_kind: "text" },
    { type: "text_delta", part: 1, delta: "Hi" },
  ];
  const state = streamed(started(), frames);
  const hello = { type: "welcome", workspace_id: "ws_1", head_seq: 9 } as v1.Server;
  const again = artifactr.welcome?.(state, hello) ?? state;
  expect(again.runs.run_1).toMatchObject({
    text: "",
    live: { thinking: "", phase: "starting", outputChars: 0, part: null, framed: false },
  });
  expect(streamed(again, frames).runs.run_1).toMatchObject({
    text: "Hi",
    live: { thinking: "Hmm." },
  });
  // A run that has ended isn't replayed, and keeps what it had.
  const ended = apply(
    state,
    envelope({ type: "run_ended", run_id: "run_1", thread_id: "thr_1", status: "stopped" }, 2),
  );
  expect(artifactr.welcome?.(ended, hello)).toBe(ended);
});

test("a run that fails, or is stopped, keeps what it streamed; one that completes has posted it", () => {
  const streaming = streamed(started(), [
    { type: "part_started", part: 0, part_kind: "thinking" },
    { type: "thinking_delta", part: 0, delta: "First," },
    { type: "part_started", part: 1, part_kind: "text" },
    { type: "text_delta", part: 1, delta: "Half a rep" },
  ]);
  const end = (status: string) =>
    envelope({ type: "run_ended", run_id: "run_1", thread_id: "thr_1", status }, 2);
  for (const status of ["failed", "stopped"]) {
    const ended = apply(streaming, end(status));
    expect(ended.runs.run_1).toMatchObject({
      status,
      text: "Half a rep",
      live: { thinking: "First," },
    });
    // Ended, it takes no more frames.
    const late = frame("run_1", { type: "text_delta", part: 1, delta: "ly" });
    expect(applyLive(ended, late, 9)).toBe(ended);
  }
  const posted = apply(
    streaming,
    envelope(
      {
        type: "message_posted",
        thread_id: "thr_1",
        message_id: "m9",
        content: "Reply",
        run_id: "run_1",
      },
      2,
    ),
  );
  expect(posted.runs.run_1).toMatchObject({ text: "", live: { thinking: "" } });
  expect(apply(posted, end("completed")).runs.run_1?.status).toBe("completed");
});

test("a paused run waits on the model again as it resumes, with its live output afresh", () => {
  const ask = { kind: "question", tool_call_id: "t1", tool_name: "ask_user", args: {} };
  const paused = apply(
    streamed(started(), [
      { type: "part_started", part: 0, part_kind: "tool_call", tool_name: "ask_user" },
      { type: "tool_args_delta", part: 0, delta: "{}" },
    ]),
    envelope({ type: "run_paused", run_id: "run_1", thread_id: "thr_1", requests: [ask] }, 2),
  );
  expect(paused.runs.run_1?.live).toMatchObject({ phase: "starting", tool: null });
  const resumed = apply(
    paused,
    envelope(
      { type: "deferred_answered", run_id: "run_1", thread_id: "thr_1", tool_call_id: "t1" },
      3,
    ),
  );
  expect(resumed.runs.run_1).toMatchObject({ status: "running", live: { phase: "starting" } });
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
      args_truncated: true,
    },
    {
      type: "tool_returned",
      run_id: "run_1",
      thread_id: "thr_1",
      tool_call_id: "t1",
      status: "retry",
      summary: "rule: Field required",
      truncated: true,
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
      argsCut: true,
      resultCut: true,
      seq: 2,
    },
    t2: {
      name: "draft_rule",
      status: "error",
      args: "",
      result: "Boom",
      argsCut: false,
      resultCut: false,
      seq: 4,
    },
  });
});

test("a run keeps the messages that started it, and the person it acts for", () => {
  const bob = {
    kind: "agent",
    thread_id: "thr_1",
    run_id: "run_1",
    on_behalf_of: { kind: "user", id: "bob" },
  };
  const state = [
    { type: "run_started", run_id: "run_1", thread_id: "thr_1", message_ids: ["m1"] },
    { type: "run_started", run_id: "run_1", thread_id: "thr_1", message_ids: ["m2"] },
  ]
    .map((event, index) => ({ ...envelope(event, index + 1), actor: bob }) as v1.EventFrame)
    .reduce(apply, artifactr.initial());
  expect(state.runs.run_1).toMatchObject({ prompt: ["m1"], actsFor: "bob", started: 2 });
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
    changedAt: "2026-10-12T00:00:00Z",
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

/** Events at the moments given, in order. */
function at(...events: [string, Record<string, unknown>][]): Workspace {
  return events
    .map(([ts, event], index) => ({ ...envelope(event, index + 1), ts }))
    .reduce(apply, artifactr.initial());
}

test("a thread and an artifact keep when they last moved; archiving isn't a change", () => {
  const made = { artifact_id: "plan_1", kind: "plan", data: {} };
  const state = at(
    ["2026-10-12T09:00:00Z", { type: "thread_created", thread_id: "thr_1", title: "Launch" }],
    ["2026-10-12T09:05:00Z", { type: "artifact_created", ...made, version: 1 }],
    [
      "2026-10-12T09:10:00Z",
      {
        type: "artifact_changed",
        ...made,
        version: 2,
        patch: { kind: "json_patch", ops: [] },
        summary: "",
      },
    ],
    [
      "2026-10-12T09:20:00Z",
      { type: "artifact_archived", artifact_id: "plan_1", kind: "plan", version: 2 },
    ],
    [
      "2026-10-12T09:30:00Z",
      { type: "message_posted", thread_id: "thr_1", message_id: "m1", content: "Hi" },
    ],
    // A message in a thread whose start the store never read: when it was active is known.
    [
      "2026-10-12T09:40:00Z",
      { type: "message_posted", thread_id: "thr_2", message_id: "m2", content: "Hello" },
    ],
  );
  expect(state.artifacts.plan_1?.changedAt).toBe("2026-10-12T09:10:00Z");
  expect(state.threads.thr_1?.activeAt).toBe("2026-10-12T09:30:00Z");
  expect(state.threads.thr_2?.activeAt).toBe("2026-10-12T09:40:00Z");
  // A thread renamed or refocused hasn't been active: its time stays.
  const refocused = apply(state, {
    ...envelope({ type: "focus_changed", thread_id: "thr_1", artifact_ids: [] }, 7),
    ts: "2026-10-12T10:00:00Z",
  });
  expect(refocused.threads.thr_1?.activeAt).toBe("2026-10-12T09:30:00Z");
});

/** A welcome frame, with the runs the server says are running. */
const welcomed = (...runs: string[]): v1.Server =>
  ({
    type: "welcome",
    workspace_id: "ws_1",
    head_seq: 9,
    active_runs: runs.map((run_id) => ({ run_id, thread_id: "thr_1" })),
  }) as v1.Server;

test("a response numbers its parts from 0: a part at or below the last begins one, and its first text part replaces the text", () => {
  // Request 1: text, then a tool call. Request 2: thinking, then the reply.
  let state = streamed(started(), [
    { type: "part_started", part: 0, part_kind: "text" },
    { type: "text_delta", part: 0, delta: "I'll draft it." },
    { type: "part_started", part: 1, part_kind: "tool_call", tool_name: "draft" },
    { type: "part_ended", part: 1 },
    { type: "part_started", part: 0, part_kind: "thinking" },
    { type: "thinking_delta", part: 0, delta: "Now the reply." },
    { type: "part_started", part: 1, part_kind: "text" },
    { type: "text_delta", part: 1, delta: "Here it is." },
  ]);
  expect(state.runs.run_1?.text).toBe("Here it is.");
  // Parallel tool calls, then the reply in the next response.
  state = streamed(started(), [
    { type: "part_started", part: 0, part_kind: "text" },
    { type: "text_delta", part: 0, delta: "Two things." },
    { type: "part_started", part: 1, part_kind: "tool_call", tool_name: "a" },
    { type: "part_started", part: 2, part_kind: "tool_call", tool_name: "b" },
    { type: "part_started", part: 0, part_kind: "text" },
    { type: "text_delta", part: 0, delta: "Both done." },
  ]);
  expect(state.runs.run_1?.text).toBe("Both done.");
  // A retry after an error starts over at 0.
  state = streamed(started(), [
    { type: "part_started", part: 0, part_kind: "text" },
    { type: "text_delta", part: 0, delta: "First try" },
    { type: "part_started", part: 0, part_kind: "text" },
    { type: "text_delta", part: 0, delta: "Second try" },
  ]);
  expect(state.runs.run_1?.text).toBe("Second try");
  // A first response of a tool call alone, then the reply.
  state = streamed(started(), [
    { type: "part_started", part: 0, part_kind: "tool_call", tool_name: "look" },
    { type: "part_ended", part: 0 },
    { type: "part_started", part: 0, part_kind: "text" },
    { type: "text_delta", part: 0, delta: "Found it." },
  ]);
  expect(state.runs.run_1).toMatchObject({ text: "Found it.", live: { reply: "writing" } });
});

test("text before a tool call is stale once the call starts, and the reply replaces it", () => {
  const state = streamed(started(), [
    { type: "part_started", part: 0, part_kind: "text" },
    { type: "text_delta", part: 0, delta: "Let me look." },
    { type: "part_started", part: 1, part_kind: "tool_call", tool_name: "look" },
  ]);
  expect(state.runs.run_1).toMatchObject({ text: "Let me look.", live: { reply: "stale" } });
});

test("a resumed run replies afresh: the words before its question go, on the answer and on the new turn's start", () => {
  const ask = { kind: "question", tool_call_id: "t1", tool_name: "ask_user", args: {} };
  const paused = apply(
    streamed(started(), [
      { type: "part_started", part: 0, part_kind: "text" },
      { type: "text_delta", part: 0, delta: "One question first." },
      { type: "part_started", part: 1, part_kind: "tool_call", tool_name: "ask_user" },
    ]),
    envelope({ type: "run_paused", run_id: "run_1", thread_id: "thr_1", requests: [ask] }, 2),
  );
  expect(paused.runs.run_1?.text).toBe("One question first.");
  const answered = apply(
    paused,
    envelope(
      { type: "deferred_answered", run_id: "run_1", thread_id: "thr_1", tool_call_id: "t1" },
      3,
    ),
  );
  expect(answered.runs.run_1).toMatchObject({ status: "running", text: "" });
  // The new turn's own start, as the log has it, starts the live output over too.
  const turn = apply(
    {
      ...paused,
      runs: { ...paused.runs, run_1: { ...paused.runs.run_1, status: "running" } },
    } as Workspace,
    envelope({ type: "run_started", run_id: "run_1", thread_id: "thr_1" }, 3),
  );
  expect(turn.runs.run_1).toMatchObject({ text: "", started: 3, live: { phase: "starting" } });
  const replied = streamed(turn, [
    { type: "part_started", part: 0, part_kind: "text" },
    { type: "text_delta", part: 0, delta: "Thanks: here." },
  ]);
  expect(replied.runs.run_1?.text).toBe("Thanks: here.");
});

test("a welcome seeds the runs the server says are running, so their frames before the replay aren't dropped", () => {
  const state = applyWelcome(artifactr.initial(), welcomed("run_7"), 1000);
  expect(state.runs.run_7).toMatchObject({ threadId: "thr_1", status: "running", started: 0 });
  const frames = [
    { type: "part_started", part: 0, part_kind: "text" },
    { type: "text_delta", part: 0, delta: "Early" },
  ];
  const early = frames.reduce((next, event) => applyLive(next, frame("run_7", event), 2000), state);
  expect(early.runs.run_7?.text).toBe("Early");
  // The replay reaches its start: what it has streamed stays, and its start is known.
  const known = apply(
    early,
    envelope({ type: "run_started", run_id: "run_7", thread_id: "thr_1", message_ids: ["m1"] }, 4),
  );
  expect(known.runs.run_7).toMatchObject({ text: "Early", started: 4, prompt: ["m1"] });
  // A run that ended while the connection was down isn't in the list: its frames change nothing.
  expect(applyLive(state, frame("run_8", frames[1] as Record<string, unknown>), 3)).toBe(state);
});

test("a delta whose part's start was lost still says what the model is doing", () => {
  const state = streamed(started(), [{ type: "text_delta", part: 0, delta: "…and so" }]);
  expect(state.runs.run_1?.live).toMatchObject({ phase: "writing", truncated: true });
  const thinking = streamed(started(), [{ type: "thinking_delta", part: 0, delta: "hm" }]);
  expect(thinking.runs.run_1?.live.phase).toBe("thinking");
  const args = streamed(started(), [{ type: "tool_args_delta", part: 0, delta: "{" }]);
  expect(args.runs.run_1?.live).toMatchObject({ phase: "tool", argsChars: 1 });
});

test("a replay that began mid-part is marked as missing its start; a welcome forgets how long it thought", () => {
  const again = applyWelcome(started(), welcomed("run_1"), 1000);
  expect(again.runs.run_1?.live.thoughtMs).toBeNull();
  const whole = streamed(again, [
    { type: "part_started", part: 0, part_kind: "text" },
    { type: "text_delta", part: 0, delta: "x" },
  ]);
  expect(whole.runs.run_1?.live).toMatchObject({ truncated: false, framed: true });
  const lost = streamed(again, [{ type: "text_delta", part: 0, delta: "x" }]);
  expect(lost.runs.run_1?.live).toMatchObject({ truncated: true, framed: true });
  // A new text part of a new response starts clean.
  const next = streamed(lost, [{ type: "part_started", part: 0, part_kind: "text" }]);
  expect(next.runs.run_1).toMatchObject({ text: "", live: { truncated: false } });
});

test("text and thinking keep their last part past the cap, and say their start went", () => {
  const long = "y".repeat(CAP - 1);
  const state = streamed(started(), [
    { type: "part_started", part: 0, part_kind: "thinking" },
    { type: "thinking_delta", part: 0, delta: long },
    { type: "thinking_delta", part: 0, delta: "zzz" },
    { type: "part_started", part: 1, part_kind: "text" },
    { type: "text_delta", part: 1, delta: long },
    { type: "text_delta", part: 1, delta: "end" },
  ]);
  const { live, text } = state.runs.run_1 as NonNullable<Workspace["runs"][string]>;
  expect(live.thinking).toHaveLength(CAP);
  expect(live.thinking.endsWith("zzz")).toBe(true);
  expect(text).toHaveLength(CAP);
  expect(text.endsWith("end")).toBe(true);
  expect(live.truncated).toBe(true);
});

test("text that arrives after the reply was posted is late, and isn't shown beside it", () => {
  const posted = apply(
    streamed(started(), [
      { type: "part_started", part: 0, part_kind: "text" },
      { type: "text_delta", part: 0, delta: "The reply" },
    ]),
    envelope(
      {
        type: "message_posted",
        thread_id: "thr_1",
        message_id: "m9",
        content: "The reply",
        run_id: "run_1",
      },
      2,
    ),
  );
  const late = streamed(posted, [{ type: "text_delta", part: 0, delta: "." }]);
  expect(late.runs.run_1?.text).toBe("");
  // A part that starts after it is a new one, and shows.
  const next = streamed(late, [
    { type: "part_started", part: 0, part_kind: "text" },
    { type: "text_delta", part: 0, delta: "More" },
  ]);
  expect(next.runs.run_1?.text).toBe("More");
});

test("the clock a durable event stamps a phase with is the caller's, so a test is deterministic", () => {
  const call = { run_id: "run_1", thread_id: "thr_1", tool_call_id: "t1", tool_name: "a" };
  const called = apply(started(), envelope({ type: "tool_called", ...call }, 2), 5000);
  expect(called.runs.run_1?.live).toMatchObject({ phase: "tool", calls: 1, since: 5000, at: 5000 });
  const started2 = apply(
    artifactr.initial(),
    envelope({ type: "run_started", run_id: "r", thread_id: "t" }, 1),
    7,
  );
  expect(started2.runs.r?.live).toMatchObject({ since: 7, at: 7 });
});

test("parallel tool calls keep the tool phase until the last returns, naming the latest", () => {
  const call = (id: string, name: string) => ({
    run_id: "run_1",
    thread_id: "thr_1",
    tool_call_id: id,
    tool_name: name,
  });
  let state = apply(started(), envelope({ type: "tool_called", ...call("t1", "a") }, 2), 1);
  state = apply(state, envelope({ type: "tool_called", ...call("t2", "b") }, 3), 2);
  expect(state.runs.run_1?.live).toMatchObject({ phase: "tool", tool: "b", calls: 2 });
  state = apply(state, envelope({ type: "tool_returned", ...call("t1", "a"), status: "ok" }, 4), 3);
  expect(state.runs.run_1?.live).toMatchObject({ phase: "tool", calls: 1 });
  state = apply(state, envelope({ type: "tool_returned", ...call("t2", "b"), status: "ok" }, 5), 4);
  expect(state.runs.run_1?.live).toMatchObject({ phase: "starting", calls: 0, tool: null });
});
