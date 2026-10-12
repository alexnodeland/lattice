/**
 * reflexr's workspace protocol: a workspace's stored rules and runs, as reflexr's own events
 * build them, and the feedback on its runs.
 *
 * reflexr's schema types an event as open, `{type, ...}`, since the application's events share
 * the log with reflexr's own. The reducer has one handler for each of reflexr's run and rule
 * events, by name, and reads their fields as JSON; every other event changes nothing here. Once
 * reflexr's schema names its own events (lattice#83), this reducer is typed like artifactr's.
 */

import type { Feedback } from "./feedback";
import type * as v1 from "./generated/reflexr.v1";
import type { Classified, Protocol, Stream } from "./stream";

export interface Run {
  readonly id: string;
  readonly rule: string;
  readonly status: "running" | "retrying" | "succeeded" | "dead_lettered" | "cancelled" | "skipped";
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

type Event = v1.EventFrame["event"];
type Handler = (state: Workspace, event: Event, envelope: v1.EventFrame) => Workspace;

function text(event: Event, field: string): string {
  const value = event[field];
  return typeof value === "string" ? value : "";
}

function count(event: Event, field: string): number {
  const value = event[field];
  return typeof value === "number" ? value : 0;
}

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

function ended(status: Run["status"]): Handler {
  return (state, event) => withRun(state, text(event, "run_id"), { status });
}

function ignore(state: Workspace): Workspace {
  return state;
}

const handlers: Readonly<Record<string, Handler>> = {
  "reflexr:rule_installed": (state, event) =>
    withRule(state, text(event, "rule"), { version: count(event, "version"), archived: false }),
  "reflexr:rule_archived": (state, event) =>
    withRule(state, text(event, "rule"), { version: count(event, "version"), archived: true }),
  "reflexr:rule_fired": (state, event) => {
    const name = text(event, "rule");
    return withRule(state, name, { firings: (state.rules[name]?.firings ?? 0) + 1 });
  },
  "reflexr:run_started": (state, event, envelope) =>
    withRun(state, text(event, "run_id"), {
      rule: text(event, "rule"),
      status: "running",
      attempt: count(event, "attempt"),
      started: envelope.seq,
    }),
  "reflexr:run_retrying": (state, event) =>
    withRun(state, text(event, "run_id"), {
      status: "retrying",
      attempt: count(event, "attempt"),
    }),
  "reflexr:run_requeued": (state, event) => {
    const id = text(event, "run_id");
    return withRun(state, id, { status: "running", retries: (state.runs[id]?.retries ?? 0) + 1 });
  },
  "reflexr:run_succeeded": ended("succeeded"),
  "reflexr:run_dead_lettered": ended("dead_lettered"),
  "reflexr:run_cancelled": ended("cancelled"),
  "reflexr:run_skipped": ended("skipped"),
  // Facts the store doesn't show: a rule's errors, resets and progress, ticks and feedback.
  "reflexr:rule_errored": ignore,
  "reflexr:rule_reset": ignore,
  "reflexr:run_progressed": ignore,
  "reflexr:tick": ignore,
  "reflexr:feedback_given": (state, event, envelope) => {
    const { target, value } = event;
    const run =
      isRecord(target) && target.kind === "run" ? state.runs[String(target.run_id)] : null;
    if (!run) {
      return state; // a firing's or a chain's, or a run before what the store read
    }
    const feedback = {
      actor: envelope.actor,
      type: text(event, "feedback_type"),
      value: isRecord(value) ? value : {},
    };
    return withRun(state, run.id, { feedback: [...run.feedback, feedback] });
  },
};

/** The state after one event. */
export function apply(state: Workspace, envelope: v1.EventFrame): Workspace {
  const handler = handlers[envelope.event.type];
  return handler ? handler(state, envelope.event, envelope) : state;
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
