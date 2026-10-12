/**
 * artifactr's thread protocol: a workspace's threads, messages, artifacts, proposals and runs, as
 * its events build them, and the runs' streaming text, as their live frames build it.
 *
 * The reducer has one handler for every event type the protocol's schema names, which the
 * compiler checks; an event type it doesn't know is kept by the log and changes nothing here.
 */

import type * as v1 from "./generated/artifactr.v1";
import type { Classified, Protocol, Stream } from "./stream";

/** The events this version of the protocol names: those whose `type` is a literal. */
export type Known = v1.Event extends infer E
  ? E extends { type: infer T }
    ? string extends T
      ? never
      : E
    : never
  : never;

export interface Message {
  readonly id: v1.MessageId;
  readonly seq: number;
  readonly actor: v1.Actor;
  readonly content: string;
  readonly kind: "message" | "notice";
  readonly runId: v1.RunId | null;
}

export interface Thread {
  readonly id: v1.ThreadId;
  readonly title: string;
  readonly mode: "edit" | "suggest";
  readonly focus: readonly v1.ArtifactId[];
  readonly messages: readonly Message[];
}

export interface Artifact {
  readonly id: v1.ArtifactId;
  readonly kind: string;
  /** The latest version the log has reached; its content is read over REST. */
  readonly version: number;
  readonly archived: boolean;
}

export interface Proposal {
  readonly id: v1.ProposalId;
  readonly threadId: v1.ThreadId | null;
  readonly status: "open" | "accept" | "reject";
}

export interface Tool {
  readonly name: string;
  /** `called` until it returns, then the status it returned with. */
  readonly status: string;
}

export interface Run {
  readonly id: v1.RunId;
  readonly threadId: v1.ThreadId;
  /** `running`, `paused`, or how it ended: `succeeded`, `failed`, `stopped` and the like. */
  readonly status: string;
  readonly tools: Readonly<Record<string, Tool>>;
  /** The text the run is streaming, until its message is posted or it ends. */
  readonly text: string;
}

export interface Workspace {
  readonly threads: Readonly<Record<v1.ThreadId, Thread>>;
  readonly artifacts: Readonly<Record<v1.ArtifactId, Artifact>>;
  readonly proposals: Readonly<Record<v1.ProposalId, Proposal>>;
  readonly runs: Readonly<Record<v1.RunId, Run>>;
}

type Handlers = {
  readonly [T in Known["type"]]: (
    state: Workspace,
    event: Extract<Known, { type: T }>,
    envelope: v1.EventFrame,
  ) => Workspace;
};

function thread(state: Workspace, id: v1.ThreadId): Thread {
  return state.threads[id] ?? { id, title: "", mode: "edit", focus: [], messages: [] };
}

function withThread(state: Workspace, id: v1.ThreadId, change: Partial<Thread>): Workspace {
  return { ...state, threads: { ...state.threads, [id]: { ...thread(state, id), ...change } } };
}

function withArtifact(state: Workspace, artifact: Artifact): Workspace {
  return { ...state, artifacts: { ...state.artifacts, [artifact.id]: artifact } };
}

function withRun(state: Workspace, id: v1.RunId, change: Partial<Run>): Workspace {
  const run = state.runs[id];
  if (!(run || change.threadId)) {
    return state; // a run that started before what the store has read
  }
  const base: Run = run ?? { id, threadId: "", status: "running", tools: {}, text: "" };
  return { ...state, runs: { ...state.runs, [id]: { ...base, ...change } } };
}

function ignore(state: Workspace): Workspace {
  return state;
}

const handlers: Handlers = {
  thread_created: (state, event) => withThread(state, event.thread_id, { title: event.title }),
  thread_mode_changed: (state, event) => withThread(state, event.thread_id, { mode: event.mode }),
  focus_changed: (state, event) =>
    withThread(state, event.thread_id, { focus: event.artifact_ids }),
  message_posted: (state, event, envelope) => {
    const message: Message = {
      id: event.message_id,
      seq: envelope.seq,
      actor: envelope.actor,
      content: event.content,
      kind: event.kind ?? "message",
      runId: event.run_id ?? null,
    };
    const next = withThread(state, event.thread_id, {
      messages: [...thread(state, event.thread_id).messages, message],
    });
    // The posted message is the authoritative text of what the run streamed.
    return event.run_id ? withRun(next, event.run_id, { text: "" }) : next;
  },
  artifact_created: (state, event) =>
    withArtifact(state, {
      id: event.artifact_id,
      kind: event.kind,
      version: event.version,
      archived: false,
    }),
  artifact_changed: (state, event) =>
    withArtifact(state, {
      id: event.artifact_id,
      kind: event.kind,
      version: event.version,
      archived: false,
    }),
  artifact_archived: (state, event) =>
    withArtifact(state, {
      id: event.artifact_id,
      kind: event.kind,
      version: event.version,
      archived: true,
    }),
  proposal_created: (state, event) => ({
    ...state,
    proposals: {
      ...state.proposals,
      [event.proposal_id]: {
        id: event.proposal_id,
        threadId: event.thread_id ?? null,
        status: "open",
      },
    },
  }),
  proposal_resolved: (state, event) => ({
    ...state,
    proposals: {
      ...state.proposals,
      [event.proposal_id]: {
        id: event.proposal_id,
        threadId: event.thread_id ?? state.proposals[event.proposal_id]?.threadId ?? null,
        status: event.decision,
      },
    },
  }),
  run_started: (state, event) =>
    withRun(state, event.run_id, { threadId: event.thread_id, status: "running" }),
  tool_called: (state, event) =>
    withRun(state, event.run_id, {
      tools: {
        ...state.runs[event.run_id]?.tools,
        [event.tool_call_id]: { name: event.tool_name, status: "called" },
      },
    }),
  tool_returned: (state, event) =>
    withRun(state, event.run_id, {
      tools: {
        ...state.runs[event.run_id]?.tools,
        [event.tool_call_id]: { name: event.tool_name ?? "", status: event.status },
      },
    }),
  run_paused: (state, event) => withRun(state, event.run_id, { status: "paused" }),
  deferred_answered: (state, event) => withRun(state, event.run_id, { status: "running" }),
  run_ended: (state, event) => withRun(state, event.run_id, { status: event.status, text: "" }),
  // Feedback and the application's own events change nothing the store shows.
  feedback_given: ignore,
  app_event: ignore,
};

/** Whether this version knows the event's type. */
export function isKnown(event: v1.Event): event is Known {
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

/** The state after a live frame: a run's text grows with each text delta. */
function live(state: Workspace, frame: v1.Server): Workspace {
  if (frame.type !== "live" || frame.event.type !== "text_delta") {
    return state;
  }
  const run = state.runs[frame.run_id];
  return run ? withRun(state, frame.run_id, { text: run.text + frame.event.delta }) : state;
}

function classify(frame: v1.Server): Classified<v1.Server, v1.CommandResult> {
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
    case "live":
      return { kind: "other", frame };
    default:
      return frame satisfies never;
  }
}

/** The id a client may choose for what a command creates; `undefined` for other commands. */
function createdId(command: v1.Command): string | null | undefined {
  switch (command.type) {
    case "create_thread":
      return command.thread_id;
    case "create_artifact":
      return command.artifact_id;
    case "propose_change":
      return command.proposal_id;
    case "post_message":
      return command.message_id;
    default:
      return undefined;
  }
}

/** artifactr's thread protocol, for a `Stream`. */
export const artifactr: Protocol<Workspace, v1.Server, v1.Command, v1.CommandResult> = {
  name: "artifactr.v1",
  initial: () => ({ threads: {}, artifacts: {}, proposals: {}, runs: {} }),
  classify,
  apply,
  other: live,
  creates: (command) => createdId(command) != null,
};

/** A store over an artifactr workspace's stream. */
export type ArtifactrStream = Stream<Workspace, v1.Server, v1.Command, v1.CommandResult, v1.Hello>;
