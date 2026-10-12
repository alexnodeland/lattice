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
      },
      {
        id: "msg_2",
        seq: 5,
        actor: { kind: "user", id: "alice" },
        content: "FYI",
        kind: "notice",
        runId: null,
      },
    ],
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
    { type: "run_ended", run_id: "run_1", thread_id: "thr_1", status: "succeeded" },
  ]
    .map((event, index) => envelope(event, 3 + index))
    .reduce(apply, state);
  expect(state.runs.run_1).toEqual({
    id: "run_1",
    threadId: "thr_1",
    status: "succeeded",
    tools: { t1: { name: "edit", status: "ok" } },
    text: "",
  });
});

test("a run pauses for an answer, and resumes when it gets one", () => {
  const paused = replay(
    { type: "run_started", run_id: "run_2", thread_id: "thr_1" },
    { type: "run_paused", run_id: "run_2", thread_id: "thr_1", requests: [] },
  );
  expect(paused.runs.run_2?.status).toBe("paused");
  const resumed = apply(
    paused,
    envelope(
      {
        type: "deferred_answered",
        run_id: "run_2",
        thread_id: "thr_1",
        tool_call_id: "t2",
        approved: true,
      },
      3,
    ),
  );
  expect(resumed.runs.run_2?.status).toBe("running");
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

test("artifacts keep their kind, latest version and whether they are archived", () => {
  const state = replay(
    { type: "artifact_created", artifact_id: "plan_1", kind: "plan", version: 1, data: {} },
    {
      type: "artifact_changed",
      artifact_id: "plan_1",
      kind: "plan",
      version: 2,
      patch: { kind: "json_patch", ops: [] },
      summary: "",
    },
    { type: "artifact_archived", artifact_id: "plan_1", kind: "plan", version: 3 },
  );
  expect(state.artifacts.plan_1).toEqual({
    id: "plan_1",
    kind: "plan",
    version: 3,
    archived: true,
  });
});

test("a proposal is open until it is accepted or rejected", () => {
  const open = replay({
    type: "proposal_created",
    proposal_id: "prop_1",
    thread_id: "thr_1",
    change: {},
  });
  expect(open.proposals.prop_1?.status).toBe("open");
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
  expect(resolved.proposals.prop_1).toEqual({ id: "prop_1", threadId: "thr_1", status: "accept" });
});

test("feedback, the application's events and unknown events change nothing", () => {
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
