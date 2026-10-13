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

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function withRun(state: Workspace, id: string, change: Partial<Run>): Workspace {
  const run: Run = state.runs[id] ?? {
    id,
    rule: "",
    status: "running",
    attempt: 1,
    retries: 0,
    started: 0,
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
    withRun(state, event.run_id, { status: "retrying", attempt: event.attempt }),
  "reflexr:run_requeued": (state, event) =>
    withRun(state, event.run_id, {
      status: "pending",
      retries: (state.runs[event.run_id]?.retries ?? 0) + 1,
    }),
  "reflexr:run_succeeded": ended("succeeded"),
  "reflexr:run_dead_lettered": ended("dead_lettered"),
  "reflexr:run_cancelled": ended("cancelled"),
  "reflexr:run_skipped": ended("skipped"),
  // Facts the store doesn't show: a rule's errors, resets and progress, and ticks.
  "reflexr:rule_errored": ignore,
  "reflexr:rule_reset": ignore,
  "reflexr:run_progressed": ignore,
  "reflexr:tick": ignore,
  "reflexr:feedback_given": (state, event, envelope) => {
    const { target, value } = event;
    const run = target.kind === "run" ? state.runs[target.run_id] : null;
    if (!run) {
      return state; // a firing's or a chain's, or a run before what the store read
    }
    const feedback = {
      actor: envelope.actor,
      type: event.feedback_type,
      value: isRecord(value) ? value : {},
    };
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
