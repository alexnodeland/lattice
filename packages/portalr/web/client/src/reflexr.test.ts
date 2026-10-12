import { expect, test } from "vitest";
import type * as v1 from "./generated/reflexr.v1";
import { apply, reflexr, type Workspace } from "./reflexr";

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
