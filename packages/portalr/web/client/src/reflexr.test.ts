import { expect, test } from "vitest";
import type * as v1 from "./generated/reflexr.v1";
import { apply, RUN_EVENTS, reflexr, type Workspace } from "./reflexr";

function replay(...events: v1.EventFrame["event"][]): Workspace {
  return events
    .map(
      (event, index) =>
        ({
          type: "event",
          seq: index + 1,
          id: `evt_${index + 1}`,
          ts: "2026-10-12T00:00:00Z",
          workspace_id: "ws_1",
          actor: { kind: "system", name: "reflexr" },
          correlation_id: "c",
          event,
        }) as v1.EventFrame,
    )
    .reduce(apply, reflexr.initial());
}

test("a stored rule has its version, its firings, and whether it is archived", () => {
  const state = replay(
    { type: "reflexr:rule_installed", rule: "ops:page", version: 1 },
    { type: "reflexr:rule_fired", rule: "ops:page", firing_id: "f1" },
    { type: "reflexr:rule_fired", rule: "ops:page", firing_id: "f2" },
    { type: "reflexr:rule_archived", rule: "ops:page", version: 1 },
  );
  expect(state.rules["ops:page"]).toEqual({
    name: "ops:page",
    version: 1,
    archived: true,
    firings: 2,
  });
});

test("a run moves through its statuses", () => {
  const steps: [v1.EventFrame["event"], string][] = [
    [{ type: "reflexr:run_started", run_id: "run_1", rule: "ops:page", attempt: 1 }, "running"],
    [{ type: "reflexr:run_retrying", run_id: "run_1", attempt: 2 }, "retrying"],
    [{ type: "reflexr:run_dead_lettered", run_id: "run_1" }, "dead_lettered"],
    [{ type: "reflexr:run_requeued", run_id: "run_1" }, "pending"],
    [{ type: "reflexr:run_succeeded", run_id: "run_1" }, "succeeded"],
  ];
  const events: v1.EventFrame["event"][] = [];
  for (const [event, status] of steps) {
    events.push(event);
    expect(replay(...events).runs.run_1?.status).toBe(status);
  }
  expect(replay(...events).runs.run_1).toEqual({
    id: "run_1",
    rule: "ops:page",
    status: "succeeded",
    attempt: 2,
    retries: 1,
    started: 1,
    reason: null,
    history: [
      {
        kind: "retried",
        seq: 4,
        actor: { kind: "system", name: "reflexr" },
        at: "2026-10-12T00:00:00Z",
        reason: null,
      },
    ],
    feedback: [],
  });
  expect(replay({ type: "reflexr:run_cancelled", run_id: "r" }).runs.r?.status).toBe("cancelled");
  expect(replay({ type: "reflexr:run_skipped", run_id: "r" }).runs.r?.status).toBe("skipped");
});

test("the application's events, and reflexr's that the store doesn't show, change nothing", () => {
  const state = replay(
    { type: "ops:alert.fired", service: "checkout" },
    { type: "reflexr:tick", schedule: "hourly" },
    { type: "reflexr:rule_reset", rule: "ops:page" },
  );
  expect(state).toEqual(reflexr.initial());
  expect(reflexr.creates({ type: "publish", event: { type: "ops:x" } })).toBe(false);
});

test("feedback on a run is kept with it; on a firing, a chain or an unread run, nowhere", () => {
  const thumbs = (target: Record<string, unknown>) => ({
    type: "reflexr:feedback_given",
    feedback_type: "thumbs",
    target,
    value: { up: false },
  });
  const state = replay(
    { type: "reflexr:run_started", run_id: "run_1", rule: "ops:page", attempt: 1 },
    thumbs({ kind: "run", run_id: "run_1" }),
    thumbs({ kind: "firing", firing_id: "fir_1" }),
    thumbs({ kind: "run", run_id: "run_9" }),
    { type: "reflexr:feedback_given", feedback_type: "thumbs", target: "run_1", value: 3 },
  );
  expect(state.runs.run_1?.feedback).toEqual([
    { actor: { kind: "system", name: "reflexr" }, type: "thumbs", value: { up: false } },
  ]);
  expect(state.runs.run_9).toBeUndefined();
});

test("a run is as new as its first attempt", () => {
  const state = replay(
    { type: "reflexr:run_started", run_id: "run_1", rule: "ops:page", attempt: 1 },
    { type: "reflexr:run_retrying", run_id: "run_1", attempt: 1 },
    { type: "reflexr:run_started", run_id: "run_1", rule: "ops:page", attempt: 2 },
  );
  expect(state.runs.run_1).toMatchObject({ attempt: 2, started: 1 });
});

test("a run keeps why it last failed, as a code, and never the error", () => {
  const state = replay(
    { type: "reflexr:run_started", run_id: "run_1", rule: "ops:page", attempt: 1 },
    {
      type: "reflexr:run_retrying",
      run_id: "run_1",
      attempt: 2,
      error: "boom: a customer's secret",
      reason: "timeout",
      next_attempt_at: "2026-10-12T00:00:01Z",
    },
    {
      type: "reflexr:run_dead_lettered",
      run_id: "run_1",
      attempts: 5,
      error: "boom: a customer's secret",
      reason: "guardrail_blocked",
    },
  );
  expect(state.runs.run_1?.reason).toBe("guardrail_blocked");
  expect(JSON.stringify(state)).not.toContain("secret");
});

test("what people did to a run is kept with who, when and why", () => {
  const by = (id: string, event: v1.EventFrame["event"], seq: number) =>
    ({
      type: "event",
      seq,
      id: `evt_${seq}`,
      ts: `2026-10-12T00:00:0${seq}Z`,
      workspace_id: "ws_1",
      actor: { kind: "user", id },
      correlation_id: "c",
      event,
    }) as v1.EventFrame;
  const state = [
    by("alice", { type: "reflexr:run_skipped", run_id: "r", rule: "x", reason: "known" }, 1),
    by("bob", { type: "reflexr:run_requeued", run_id: "r", rule: "x" }, 2),
    by("carol", { type: "reflexr:run_cancelled", run_id: "r", rule: "x" }, 3),
  ].reduce(apply, reflexr.initial());
  expect(state.runs.r?.history).toEqual([
    {
      kind: "skipped",
      seq: 1,
      actor: { kind: "user", id: "alice" },
      at: "2026-10-12T00:00:01Z",
      reason: "known",
    },
    {
      kind: "retried",
      seq: 2,
      actor: { kind: "user", id: "bob" },
      at: "2026-10-12T00:00:02Z",
      reason: null,
    },
    {
      kind: "cancelled",
      seq: 3,
      actor: { kind: "user", id: "carol" },
      at: "2026-10-12T00:00:03Z",
      reason: null,
    },
  ]);
  expect(state.runs.r?.status).toBe("cancelled");
  expect(state.runs.r?.retries).toBe(1);
});

test("a retry or a success ends why the last attempt failed", () => {
  const failed = [
    { type: "reflexr:run_started", run_id: "r", rule: "x", attempt: 1 },
    {
      type: "reflexr:run_dead_lettered",
      run_id: "r",
      rule: "x",
      attempts: 1,
      error: "e",
      reason: "timeout",
    },
  ] as v1.EventFrame["event"][];
  expect(replay(...failed).runs.r?.reason).toBe("timeout");
  expect(
    replay(...failed, { type: "reflexr:run_requeued", run_id: "r", rule: "x" }).runs.r?.reason,
  ).toBeNull();
  expect(
    replay(...failed, { type: "reflexr:run_succeeded", run_id: "r", rule: "x" }).runs.r?.reason,
  ).toBeNull();
});

test("the events a stream of runs asks for are the ones that make a run, and are all known", () => {
  expect(RUN_EVENTS.every((type) => type.startsWith("reflexr:run_"))).toBe(true);
  // Each of them changes a run in the store, which only an event with a handler does.
  for (const type of RUN_EVENTS) {
    const state = replay({
      type,
      run_id: "r",
      rule: "x",
      attempt: 1,
      attempts: 1,
      error: "e",
      next_attempt_at: "2026-10-12T00:00:00Z",
    } as v1.EventFrame["event"]);
    expect(state.runs.r, type).toBeDefined();
  }
});
