/**
 * reflexr's workspace protocol: a workspace's stored rules and runs, as reflexr's own events
 * build them, and the feedback on its runs.
 *
 * The reducer has one handler for every event of reflexr's own that the protocol's schema names,
 * which the compiler checks; the application's events, and any this version doesn't know, are
 * kept by the log and change nothing here.
 */

import type { Feedback } from "./feedback";
import type * as v1 from "./generated/reflexr.v1";
import type { Classified, Protocol, Stream } from "./stream";

/** reflexr's own events, which this version of the protocol names: those whose `type` is a literal. */
export type Known = v1.LoggedEvent extends infer E
  ? E extends { type: infer T }
    ? string extends T
      ? never
      : E
    : never
  : never;

/** What a person did to a run: made it runnable again, skipped it, or cancelled it. */
export interface Intervention {
  readonly kind: "retried" | "skipped" | "cancelled";
  /** Who did it, as the log recorded. */
  readonly actor: v1.EventFrame["actor"];
  /** When, as the log recorded: an ISO time. */
  readonly at: string;
  /** Why, if they said. */
  readonly reason: string | null;
}

export interface Run {
  readonly id: string;
  readonly rule: string;
  /** Queued for its next attempt (`pending`), running, waiting to retry, or how it ended. */
  readonly status:
    | "pending"
    | "running"
    | "retrying"
    | "succeeded"
    | "dead_lettered"
    | "cancelled"
    | "skipped";
  readonly attempt: number;
  /** How many times a person retried it: each retry starts its attempts again. */
  readonly retries: number;
  /** The `seq` it started at: the later, the newer. */
  readonly started: number;
  /** A stable code for why the last attempt failed, such as `guardrail_blocked`; never the error. */
  readonly reason: string | null;
  /** What people did to it, oldest first. */
  readonly history: readonly Intervention[];
  /** The feedback given on it, oldest first. */
  readonly feedback: readonly Feedback<v1.EventFrame["actor"]>[];
}

export interface Rule {
  readonly name: string;
  readonly version: number;
  readonly archived: boolean;
  readonly firings: number;
}

export interface Workspace {
  readonly rules: Readonly<Record<string, Rule>>;
  readonly runs: Readonly<Record<string, Run>>;
}

type Handlers = {
  readonly [T in Known["type"]]: (
    state: Workspace,
    event: Extract<Known, { type: T }>,
    envelope: v1.EventFrame,
  ) => Workspace;
};

function withRun(state: Workspace, id: string, change: Partial<Run>): Workspace {
  const run: Run = state.runs[id] ?? {
    id,
    rule: "",
    status: "running",
    attempt: 1,
    retries: 0,
    started: 0,
    reason: null,
    history: [],
    feedback: [],
  };
  return { ...state, runs: { ...state.runs, [id]: { ...run, ...change } } };
}

function withRule(state: Workspace, name: string, change: Partial<Rule>): Workspace {
  const rule = state.rules[name] ?? { name, version: 0, archived: false, firings: 0 };
  return { ...state, rules: { ...state.rules, [name]: { ...rule, ...change } } };
}

function ended(status: Run["status"]) {
  return (state: Workspace, event: { readonly run_id: string }): Workspace =>
    withRun(state, event.run_id, { status });
}

/** A run a person changed: its new status, if any, and what they did, with who and when. */
function intervened(
  kind: Intervention["kind"],
  status: Run["status"],
  extra: (state: Workspace, id: string) => Partial<Run> = () => ({}),
) {
  return (
    state: Workspace,
    event: { readonly run_id: string; readonly reason?: string | null },
    envelope: v1.EventFrame,
  ): Workspace => {
    const history = state.runs[event.run_id]?.history ?? [];
    const step: Intervention = {
      kind,
      actor: envelope.actor,
      at: envelope.ts,
      reason: event.reason ?? null,
    };
    return withRun(state, event.run_id, {
      status,
      history: [...history, step],
      ...extra(state, event.run_id),
    });
  };
}

function ignore(state: Workspace): Workspace {
  return state;
}

const handlers: Handlers = {
  "reflexr:rule_installed": (state, event) =>
    withRule(state, event.rule, { version: event.version, archived: false }),
  "reflexr:rule_archived": (state, event) =>
    withRule(state, event.rule, { version: event.version, archived: true }),
  "reflexr:rule_fired": (state, event) =>
    withRule(state, event.rule, { firings: (state.rules[event.rule]?.firings ?? 0) + 1 }),
  "reflexr:run_started": (state, event, envelope) =>
    withRun(state, event.run_id, {
      rule: event.rule,
      status: "running",
      attempt: event.attempt,
      // Its first attempt's `seq`: a later attempt doesn't make the run newer.
      started: state.runs[event.run_id]?.started || envelope.seq,
    }),
  "reflexr:run_retrying": (state, event) =>
    withRun(state, event.run_id, {
      status: "retrying",
      attempt: event.attempt,
      reason: event.reason ?? null,
    }),
  "reflexr:run_requeued": intervened("retried", "pending", (state, id) => ({
    retries: (state.runs[id]?.retries ?? 0) + 1,
  })),
  "reflexr:run_succeeded": ended("succeeded"),
  "reflexr:run_dead_lettered": (state, event) =>
    withRun(state, event.run_id, { status: "dead_lettered", reason: event.reason ?? null }),
  "reflexr:run_cancelled": intervened("cancelled", "cancelled"),
  "reflexr:run_skipped": intervened("skipped", "skipped"),
  // Facts the store doesn't show: a rule's errors, resets and progress, and ticks.
  "reflexr:rule_errored": ignore,
  "reflexr:rule_reset": ignore,
  "reflexr:run_progressed": ignore,
  "reflexr:tick": ignore,
  "reflexr:feedback_given": (state, event, envelope) => {
    const { target } = event;
    const run = target.kind === "run" ? state.runs[target.run_id] : null;
    if (!run) {
      return state; // a firing's or a chain's, or a run before what the store read
    }
    const feedback = { actor: envelope.actor, type: event.feedback_type, value: event.value };
    return withRun(state, run.id, { feedback: [...run.feedback, feedback] });
  },
};

/** Whether the event is one of reflexr's own that this version knows. */
export function isKnown(event: v1.LoggedEvent): event is Known {
  return Object.hasOwn(handlers, event.type);
}

/** The state after one event. */
export function apply(state: Workspace, envelope: v1.EventFrame): Workspace {
  const { event } = envelope;
  if (!isKnown(event)) {
    return state;
  }
  // A correlated union: `handlers[event.type]` takes this very event, which the compiler can't
  // follow through the lookup.
  const handler = handlers[event.type] as (
    state: Workspace,
    event: Known,
    envelope: v1.EventFrame,
  ) => Workspace;
  return handler(state, event, envelope);
}

function classify(frame: v1.ServerFrame): Classified<v1.ServerFrame, v1.CommandResult> {
  switch (frame.type) {
    case "welcome":
      return { kind: "welcome", headSeq: frame.head_seq, reset: frame.reset ?? false };
    case "replay_complete":
      return { kind: "replay_complete" };
    case "event":
      return { kind: "event", envelope: frame };
    case "command_result":
      return { kind: "result", result: frame };
    case "error":
      return { kind: "error", message: frame.message };
    default:
      return frame satisfies never;
  }
}

/** reflexr's workspace protocol, for a `Stream`. A publish with an `id` is idempotent itself. */
export const reflexr: Protocol<Workspace, v1.ServerFrame, v1.Command, v1.CommandResult> = {
  name: "reflexr.v1",
  initial: () => ({ rules: {}, runs: {} }),
  classify,
  apply,
  other: (state) => state,
  creates: () => false,
};

/** A store over a reflexr workspace's stream. */
export type ReflexrStream = Stream<
  Workspace,
  v1.ServerFrame,
  v1.Command,
  v1.CommandResult,
  v1.Hello
>;
