/**
 * reflexr's workspace protocol: a workspace's stored rules and runs, as reflexr's own events
 * build them.
 *
 * reflexr's schema types an event as open, `{type, ...}`, since the application's events share
 * the log with reflexr's own. The reducer has one handler for each of reflexr's run and rule
 * events, by name, and reads their fields as JSON; every other event changes nothing here.
 */

import type * as v1 from "./generated/reflexr.v1";
import type { Protocol } from "./stream";

export interface Run {
  readonly id: string;
  readonly rule: string;
  /** `running`, `retrying`, `succeeded`, `dead_lettered`, `cancelled` or `skipped`. */
  readonly status: string;
  readonly attempt: number;
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
type Handler = (state: Workspace, event: Event) => Workspace;

function text(event: Event, field: string): string {
  const value = event[field];
  return typeof value === "string" ? value : "";
}

function count(event: Event, field: string): number {
  const value = event[field];
  return typeof value === "number" ? value : 0;
}

function withRun(state: Workspace, id: string, change: Partial<Run>): Workspace {
  const run = state.runs[id] ?? { id, rule: "", status: "running", attempt: 1 };
  return { ...state, runs: { ...state.runs, [id]: { ...run, ...change } } };
}

function withRule(state: Workspace, name: string, change: Partial<Rule>): Workspace {
  const rule = state.rules[name] ?? { name, version: 0, archived: false, firings: 0 };
  return { ...state, rules: { ...state.rules, [name]: { ...rule, ...change } } };
}

function ended(status: string): Handler {
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
  "reflexr:run_started": (state, event) =>
    withRun(state, text(event, "run_id"), {
      rule: text(event, "rule"),
      status: "running",
      attempt: count(event, "attempt"),
    }),
  "reflexr:run_retrying": (state, event) =>
    withRun(state, text(event, "run_id"), {
      status: "retrying",
      attempt: count(event, "attempt"),
    }),
  "reflexr:run_requeued": ended("running"),
  "reflexr:run_succeeded": ended("succeeded"),
  "reflexr:run_dead_lettered": ended("dead_lettered"),
  "reflexr:run_cancelled": ended("cancelled"),
  "reflexr:run_skipped": ended("skipped"),
  // Facts the store doesn't show: a rule's errors, resets and progress, ticks and feedback.
  "reflexr:rule_errored": ignore,
  "reflexr:rule_reset": ignore,
  "reflexr:run_progressed": ignore,
  "reflexr:tick": ignore,
  "reflexr:feedback_given": ignore,
};

/** The state after one event. */
export function apply(state: Workspace, envelope: v1.EventFrame): Workspace {
  const handler = handlers[envelope.event.type];
  return handler ? handler(state, envelope.event) : state;
}

/** reflexr's workspace protocol, for a `Stream`. A publish with an `id` is idempotent itself. */
export const reflexr: Protocol<Workspace, v1.ServerFrame, v1.Command> = {
  name: "reflexr.v1",
  initial: () => ({ rules: {}, runs: {} }),
  apply,
  creates: () => false,
};
