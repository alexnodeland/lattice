/**
 * artifactr's thread protocol: a workspace's threads, messages, artifacts, proposals and runs, as
 * its events build them, and the runs' streaming text, as their live frames build it.
 *
 * The reducer has one handler for every event type the protocol's schema names, which the
 * compiler checks; an event type it doesn't know is kept by the log and changes nothing here.
 */

import type { Feedback as Given } from "./feedback";
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

/** Feedback someone gave on a message, an artifact or a turn; on an artifact, on one version. */
export type Feedback = Given<v1.Actor> & { readonly version?: number };

export interface Message {
  readonly id: v1.MessageId;
  readonly seq: number;
  readonly actor: v1.Actor;
  readonly content: string;
  readonly kind: "message" | "notice";
  readonly runId: v1.RunId | null;
  /** The feedback given on it, oldest first. */
  readonly feedback: readonly Feedback[];
}

export interface Thread {
  readonly id: v1.ThreadId;
  readonly title: string;
  readonly mode: "edit" | "suggest";
  readonly focus: readonly v1.ArtifactId[];
  readonly messages: readonly Message[];
  /** The `seq` of its latest message, or of its start: how recently it was active. */
  readonly active: number;
  /** When that was, as its event says, or null for a thread the store hasn't seen begin. */
  readonly activeAt: string | null;
}

export interface Artifact {
  readonly id: v1.ArtifactId;
  readonly kind: string;
  /** The latest version the log has reached; its content is read over REST. */
  readonly version: number;
  readonly archived: boolean;
  /** The thread it was made in, and the `seq` it was made at: where a thread shows it. */
  readonly threadId: v1.ThreadId | null;
  readonly seq: number;
  /** The feedback given on its latest version, oldest first: each version is judged anew. */
  readonly feedback: readonly Feedback[];
  /** When its latest version was made, as its event says. */
  readonly changedAt: string;
}

export interface Proposal {
  readonly id: v1.ProposalId;
  readonly threadId: v1.ThreadId | null;
  /** The run that proposed it, if the agent did. */
  readonly runId: v1.RunId | null;
  /** What it would change, or null if it was resolved before what the store read. */
  readonly change: v1.ProposalCreated["change"] | null;
  readonly rationale: string | null;
  readonly status: "open" | "accept" | "reject";
}

export interface Tool {
  readonly name: string;
  /** `called` until it returns, then the status it returned with: `ok`, `error` or `retry`. */
  readonly status: string;
  /** Its arguments, as the run recorded them: JSON, cut short past the run's limit. */
  readonly args: string;
  /** What it returned, or why it failed or was refused, as recorded; empty until it returns. */
  readonly result: string;
  /** Whether the run cut `args`, or `result`, short at its limit. */
  readonly argsCut: boolean;
  readonly resultCut: boolean;
  /** The `seq` it was called at: where its thread shows it. */
  readonly seq: number;
}

/** The deferred tool that asks questions with options (artifactr ADR-0083). */
const ASK_USER = "ask_user";

/**
 * A request to `ask_user` a run paused on, where its thread shows it, and its answer once given:
 * for the run's life, so a thread keeps what was asked and what was chosen.
 */
export interface Question {
  readonly request: v1.DeferredRequest;
  /** The `seq` of the pause that asked it. */
  readonly seq: number;
  /** The answer, as sent, and who sent it; null until it is answered. */
  readonly answer: { readonly value: v1.JsonValue; readonly actor: v1.Actor } | null;
}

/** A request a paused run asked, answered, and who answered it. */
export interface Answered {
  readonly request: v1.DeferredRequest;
  readonly actor: v1.Actor;
}

/** What a run is doing: waiting on the model, thinking, on a tool call, or writing its reply. */
export type Phase = "starting" | "thinking" | "tool" | "writing";

/**
 * What a run is doing right now, as its live frames say (portalr ADR-0083). Live output is never
 * stored: a reconnect starts it afresh from what the server replays, and the posted message is
 * the reply.
 */
export interface Live {
  readonly phase: Phase;
  /** The tool whose call is being prepared, or the latest running, in the `tool` phase. */
  readonly tool: string | null;
  /** How many of its calls run: their arguments complete, and each call on the log. */
  readonly calls: number;
  /** The characters of the call's arguments streamed so far. */
  readonly argsChars: number;
  /** The model's thinking, as streamed; empty where the model shows none; its last part past `CAP`. */
  readonly thinking: string;
  /** The milliseconds spent in thinking parts that have ended; null where a reconnect lost some. */
  readonly thoughtMs: number | null;
  /** Every character the model produced this turn: text, thinking and arguments, for an estimate. */
  readonly outputChars: number;
  /** When the phase began, and when the last frame came, by the browser's clock; 0 before any. */
  readonly since: number;
  readonly at: number;
  /**
   * The index of the last part the model started, of any kind: a response numbers its parts
   * from 0, so one at or below it begins a new response, whose first text part replaces the text.
   */
  readonly part: number | null;
  /**
   * What the text is: `pending`, until the response under way begins its text, which replaces
   * what is there; `writing`, this response's reply; `stale`, what the model wrote before calling
   * a tool, which isn't the reply; `posted`, the reply once posted, so text that still arrives
   * is late and isn't kept.
   */
  readonly reply: "pending" | "writing" | "stale" | "posted";
  /** Whether the start of the text or thinking is missing: cut to its cap, or lost to a reconnect. */
  readonly truncated: boolean;
  /** Whether a frame has come since the connection was welcomed. */
  readonly framed: boolean;
}

/** The most characters of text or thinking kept, from the end; the start goes, as `truncated`. */
export const CAP = 65_536;

export interface Run {
  readonly id: v1.RunId;
  readonly threadId: v1.ThreadId;
  /** `running`, `paused`, or how it ended. */
  readonly status: "running" | "paused" | v1.RunEnded["status"];
  readonly tools: Readonly<Record<string, Tool>>;
  /**
   * The text the run is streaming, until its message is posted; a run that failed or was stopped
   * keeps what it had streamed, so what it was writing isn't lost with it.
   */
  readonly text: string;
  readonly live: Live;
  /** What a paused run waits on: questions to answer and calls to approve, until each is. */
  readonly requests: readonly v1.DeferredRequest[];
  /**
   * The requests it paused on that are answered, and by whom, oldest first: until it pauses again
   * or ends, so a form stays where it was asked and says who answered it.
   */
  readonly answered: readonly Answered[];
  /** The `seq` it started at: the later, the newer. */
  readonly started: number;
  /** When it started, as the log's event says; none before it has. */
  readonly startedAt?: string;
  /** The `seq` it ended at, or null while it hasn't. */
  readonly ended: number | null;
  /** Why it failed, as its `run_ended` says: what happened, and a code for it, where known. */
  readonly error: string | null;
  readonly reason: string | null;
  /** The messages its first start carried out, oldest first: what started it. */
  readonly prompt: readonly v1.MessageId[];
  /** The person its latest start acts for, or null where it acts for no person. */
  readonly actsFor: string | null;
  /** What it asked through `ask_user`, oldest first, answered or not. */
  readonly questions: readonly Question[];
  /** The feedback given on the turn, oldest first. */
  readonly feedback: readonly Feedback[];
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
    /** The browser's clock, for a run's phase; `apply` reads it, a test gives it. */
    now: number,
  ) => Workspace;
};

function thread(state: Workspace, id: v1.ThreadId): Thread {
  return (
    state.threads[id] ?? {
      id,
      title: "",
      mode: "edit",
      focus: [],
      messages: [],
      active: 0,
      activeAt: null,
    }
  );
}

function withThread(state: Workspace, id: v1.ThreadId, change: Partial<Thread>): Workspace {
  return { ...state, threads: { ...state.threads, [id]: { ...thread(state, id), ...change } } };
}

/**
 * Where an artifact's event says it was made: its thread, and the `seq` of the first event of it
 * the store saw, which for an artifact made before the store read the log is a later one's.
 */
const madeAt = (event: { thread_id?: v1.ThreadId | null }, envelope: v1.EventFrame) => ({
  threadId: event.thread_id ?? null,
  seq: envelope.seq,
  at: envelope.ts,
});

/** An artifact's event: where it was made is kept from its first, as `madeAt` reads it. */
function withArtifact(
  state: Workspace,
  artifact: Omit<Artifact, "feedback" | "threadId" | "seq" | "changedAt">,
  made: { threadId: v1.ThreadId | null; seq: number; at: string },
): Workspace {
  const before = state.artifacts[artifact.id];
  const feedback = before?.version === artifact.version ? before.feedback : [];
  const where = before
    ? { threadId: before.threadId, seq: before.seq }
    : { threadId: made.threadId, seq: made.seq };
  return {
    ...state,
    artifacts: {
      ...state.artifacts,
      // Archiving changes nothing of what it holds: when it last changed stays as it was.
      [artifact.id]: {
        ...artifact,
        ...where,
        feedback,
        changedAt: artifact.archived && before ? before.changedAt : made.at,
      },
    },
  };
}

/** A run's live state before any frame, or again after a reconnect's replay starts it over. */
const fresh = (now: number, change: Partial<Live> = {}): Live => ({
  phase: "starting",
  tool: null,
  calls: 0,
  argsChars: 0,
  thinking: "",
  thoughtMs: 0,
  outputChars: 0,
  since: now,
  at: now,
  part: null,
  reply: "pending",
  truncated: false,
  framed: false,
  ...change,
});

/** A run's live state in `phase` from `now`, with what the phase changes. */
function phased(live: Live, phase: Phase, now: number, change: Partial<Live> = {}): Live {
  return { ...live, ...change, phase, since: live.phase === phase ? live.since : now, at: now };
}

/** A running run's live state changed; a run that has ended, or paused, is left as it is. */
function withLive(state: Workspace, id: v1.RunId, change: (live: Live) => Live): Workspace {
  const run = state.runs[id];
  return run?.status === "running" ? withRun(state, id, { live: change(run.live) }) : state;
}

/** `text` with `more` on its end, kept to `CAP` from the end: whether it was cut, and the rest. */
function appended(text: string, more: string): readonly [boolean, string] {
  const whole = text + more;
  return whole.length > CAP ? [true, whole.slice(whole.length - CAP)] : [false, whole];
}

function withRun(state: Workspace, id: v1.RunId, change: Partial<Run>): Workspace {
  const run = state.runs[id];
  if (!(run || change.threadId)) {
    return state; // a run that started before what the store has read
  }
  const base: Run = run ?? {
    id,
    threadId: "",
    status: "running",
    tools: {},
    text: "",
    live: fresh(0),
    requests: [],
    answered: [],
    started: 0,
    ended: null,
    error: null,
    reason: null,
    prompt: [],
    actsFor: null,
    questions: [],
    feedback: [],
  };
  return { ...state, runs: { ...state.runs, [id]: { ...base, ...change } } };
}

function ignore(state: Workspace): Workspace {
  return state;
}

const handlers: Handlers = {
  thread_created: (state, event, envelope) =>
    withThread(state, event.thread_id, {
      title: event.title,
      active: envelope.seq,
      activeAt: envelope.ts,
    }),
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
      feedback: [],
    };
    const next = withThread(state, event.thread_id, {
      messages: [...thread(state, event.thread_id).messages, message],
      active: envelope.seq,
      activeAt: envelope.ts,
    });
    // The posted message is the authoritative text of what the run streamed, and its thinking
    // went into it: neither is kept.
    const run = event.run_id && next.runs[event.run_id];
    return run
      ? withRun(next, run.id, {
          text: "",
          live: { ...run.live, thinking: "", reply: "posted" },
        })
      : next;
  },
  artifact_created: (state, event, envelope) =>
    withArtifact(
      state,
      { id: event.artifact_id, kind: event.kind, version: event.version, archived: false },
      madeAt(event, envelope),
    ),
  artifact_changed: (state, event, envelope) =>
    withArtifact(
      state,
      { id: event.artifact_id, kind: event.kind, version: event.version, archived: false },
      madeAt(event, envelope),
    ),
  artifact_archived: (state, event, envelope) =>
    withArtifact(
      state,
      { id: event.artifact_id, kind: event.kind, version: event.version, archived: true },
      madeAt(event, envelope),
    ),
  proposal_created: (state, event) => ({
    ...state,
    proposals: {
      ...state.proposals,
      [event.proposal_id]: {
        id: event.proposal_id,
        threadId: event.thread_id ?? null,
        runId: event.run_id ?? null,
        change: event.change,
        rationale: event.rationale ?? null,
        status: "open",
      },
    },
  }),
  proposal_resolved: (state, event) => {
    const proposal = state.proposals[event.proposal_id];
    return {
      ...state,
      proposals: {
        ...state.proposals,
        [event.proposal_id]: {
          id: event.proposal_id,
          threadId: event.thread_id ?? proposal?.threadId ?? null,
          runId: proposal?.runId ?? null,
          change: proposal?.change ?? null,
          rationale: proposal?.rationale ?? null,
          status: event.decision,
        },
      },
    };
  },
  run_started: (state, event, envelope, now) => {
    const run = state.runs[event.run_id];
    const first = run?.prompt.length ? undefined : event.message_ids;
    const { actor } = envelope;
    // A new turn's start, or a run's first, starts its live output over; one the welcome seeded
    // from the server's list of running runs may have taken frames already, which it keeps.
    const seeded = run !== undefined && run.started === 0 && run.status === "running";
    return withRun(state, event.run_id, {
      threadId: event.thread_id,
      status: "running",
      started: envelope.seq,
      startedAt: envelope.ts,
      ...(!seeded && { text: "", live: fresh(now) }),
      ...(first && { prompt: first }),
      ...(actor.kind === "agent" &&
        actor.on_behalf_of?.kind === "user" && {
          actsFor: actor.on_behalf_of.id,
        }),
    });
  },
  tool_called: (state, event, envelope, now) =>
    withRun(withLive(state, event.run_id, running(event.tool_name, now)), event.run_id, {
      tools: {
        ...state.runs[event.run_id]?.tools,
        [event.tool_call_id]: {
          name: event.tool_name,
          status: "called",
          args: event.args_summary ?? "",
          result: "",
          argsCut: event.args_truncated ?? false,
          resultCut: false,
          seq: envelope.seq,
        },
      },
    }),
  tool_returned: (state, event, envelope, now) => {
    const called = state.runs[event.run_id]?.tools[event.tool_call_id];
    return withRun(withLive(state, event.run_id, returned(now)), event.run_id, {
      tools: {
        ...state.runs[event.run_id]?.tools,
        [event.tool_call_id]: {
          name: event.tool_name || (called?.name ?? ""),
          status: event.status,
          args: called?.args ?? "",
          result: event.summary ?? "",
          argsCut: called?.argsCut ?? false,
          resultCut: event.truncated ?? false,
          seq: called?.seq ?? envelope.seq,
        },
      },
    });
  },
  run_paused: (state, event, envelope, now) => {
    const asked = event.requests
      .filter((request) => request.tool_name === ASK_USER)
      .map((request) => ({ request, seq: envelope.seq, answer: null }));
    return withRun(withLive(state, event.run_id, returned(now, true)), event.run_id, {
      status: "paused",
      requests: event.requests,
      answered: [],
      questions: [...(state.runs[event.run_id]?.questions ?? []), ...asked],
    });
  },
  deferred_answered: (state, event, envelope, now) => {
    const run = state.runs[event.run_id];
    const asked = run?.requests ?? [];
    const requests = asked.filter((request) => request.tool_call_id !== event.tool_call_id);
    const answered = asked
      .filter((request) => request.tool_call_id === event.tool_call_id)
      .map((request) => ({ request, actor: envelope.actor }));
    // A paused run resumes once every request it paused on has its answer.
    const resumes = run?.status === "paused" && requests.length === 0;
    const answer = { value: event.answer ?? null, actor: envelope.actor };
    return withRun(state, event.run_id, {
      requests,
      answered: [...(run?.answered ?? []), ...answered],
      questions: (run?.questions ?? []).map((question) =>
        question.request.tool_call_id === event.tool_call_id && question.answer === null
          ? { ...question, answer }
          : question,
      ),
      // The reply comes from the turn that resumes, not from the words before the question.
      ...(resumes && { status: "running", text: "", live: fresh(now) }),
    });
  },
  run_ended: (state, event, envelope, now) => {
    const run = state.runs[event.run_id];
    // A run that completed posted its reply; one that failed, or was stopped, keeps what it
    // had streamed, and its thinking, until the page is left: neither is kept anywhere else.
    const kept = event.status !== "completed";
    return withRun(state, event.run_id, {
      status: event.status,
      text: kept ? (run?.text ?? "") : "",
      ...(run && { live: { ...run.live, thinking: kept ? run.live.thinking : "", at: now } }),
      requests: [],
      answered: [],
      ended: envelope.seq,
      error: event.error ?? null,
      reason: event.reason ?? null,
    });
  },
  feedback_given: (state, event, envelope) => {
    const feedback: Feedback = {
      actor: envelope.actor,
      type: event.feedback_type,
      value: event.value,
    };
    // Feedback on what the store hasn't read, or on a whole thread, has nowhere to go.
    const { target } = event;
    switch (target.kind) {
      case "message": {
        const messages = state.threads[target.thread_id]?.messages ?? [];
        if (!messages.some(({ id }) => id === target.message_id)) {
          return state;
        }
        return withThread(state, target.thread_id, {
          messages: messages.map((message) =>
            message.id === target.message_id
              ? { ...message, feedback: [...message.feedback, feedback] }
              : message,
          ),
        });
      }
      case "artifact": {
        const artifact = state.artifacts[target.artifact_id];
        if (artifact?.version !== target.version) {
          return state; // an earlier version's, or an artifact the store hasn't read
        }
        const judged = { ...feedback, version: target.version };
        const given = { ...artifact, feedback: [...artifact.feedback, judged] };
        return { ...state, artifacts: { ...state.artifacts, [artifact.id]: given } };
      }
      case "turn": {
        const run = state.runs[target.run_id];
        return run ? withRun(state, run.id, { feedback: [...run.feedback, feedback] }) : state;
      }
      case "thread":
        return state;
      default:
        return target satisfies never;
    }
  },
  // The application's own events change nothing the store shows.
  app_event: ignore,
};

/** Whether this version knows the event's type. */
export function isKnown(event: v1.Event): event is Known {
  return Object.hasOwn(handlers, event.type);
}

/** The state after one event. */
export function apply(state: Workspace, envelope: v1.EventFrame, now = Date.now()): Workspace {
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
    now: number,
  ) => Workspace;
  return handler(state, event, envelope, now);
}

/** A tool's call is on the log, its arguments complete: the tool runs, beside any already. */
const running = (tool: string, now: number) => (live: Live) =>
  phased(live, "tool", now, { tool, calls: live.calls + 1 });

/**
 * A tool returned: the model is waited on again once none runs; or the run paused, which ends
 * its calls.
 */
const returned =
  (now: number, all = false) =>
  (live: Live) => {
    const calls = all ? 0 : Math.max(0, live.calls - 1);
    return calls > 0
      ? { ...live, calls, at: now }
      : phased(live, "starting", now, { tool: null, calls: 0, argsChars: 0 });
  };

/**
 * The state after a live frame, at `now`: a running run's text grows with each text delta, its
 * thinking with each thinking delta, and its phase follows the parts the model starts, or the
 * deltas where their part's start was lost. A part whose index is at or below the last part's
 * begins a new response, whose first text part replaces the text: what the model wrote before a
 * tool call isn't the reply. Text after the reply was posted is late, and isn't kept. Frames for
 * a run the store doesn't hold, or one not running, change nothing. The server keeps a run's
 * last 1,024 frames: a replay of a longer run is short its start, which the first frame shows.
 */
export function applyLive(state: Workspace, frame: v1.Server, now: number): Workspace {
  if (frame.type !== "live") {
    return state;
  }
  const run = state.runs[frame.run_id];
  if (run?.status !== "running") {
    return state;
  }
  const { event } = frame;
  // The first frame after a welcome that isn't a part's start: the start of what streamed was
  // lost before the replay.
  const live: Live = run.live.framed
    ? run.live
    : {
        ...run.live,
        framed: true,
        truncated: run.live.truncated || event.type !== "part_started",
      };
  const more = (chars: number): Partial<Live> => ({ outputChars: live.outputChars + chars });
  switch (event.type) {
    case "part_started": {
      // A part at or below the last begins a new response; so does one after text whose own
      // part's start was lost, as what response that was isn't known.
      const again = live.part === null ? live.reply === "writing" : event.part <= live.part;
      const reply = again || live.reply === "posted" ? "pending" : live.reply;
      switch (event.part_kind) {
        case "text": {
          const replaces = reply !== "writing";
          return withRun(state, run.id, {
            text: replaces ? "" : run.text,
            live: phased(live, "writing", now, {
              part: event.part,
              reply: "writing",
              truncated: replaces ? false : live.truncated,
            }),
          });
        }
        case "thinking":
          return withLive(state, run.id, (was) =>
            phased(was, "thinking", now, { part: event.part, reply }),
          );
        case "tool_call":
          return withLive(state, run.id, (was) =>
            phased(was, "tool", now, {
              part: event.part,
              // Text before a tool call is what the model said it would do, not the reply.
              reply: reply === "writing" && run.text !== "" ? "stale" : reply,
              tool: event.tool_name ?? null,
              argsChars: 0,
            }),
          );
        default:
          return state;
      }
    }
    case "text_delta": {
      if (live.reply === "posted") {
        return withLive(state, run.id, () => ({ ...live, at: now }));
      }
      const [cut, text] = appended(run.text, event.delta);
      return withRun(state, run.id, {
        text,
        live: phased(live, "writing", now, {
          ...more(event.delta.length),
          reply: "writing",
          truncated: live.truncated || cut,
        }),
      });
    }
    case "thinking_delta": {
      const [cut, thinking] = appended(live.thinking, event.delta);
      return withLive(state, run.id, () =>
        phased(live, "thinking", now, {
          ...more(event.delta.length),
          thinking,
          truncated: live.truncated || cut,
        }),
      );
    }
    case "tool_args_delta":
      return withLive(state, run.id, () =>
        phased(live, "tool", now, {
          ...more(event.delta.length),
          argsChars: live.argsChars + event.delta.length,
        }),
      );
    case "part_ended":
      // A thinking part's time is counted as it ends; the next part says what comes next.
      return withLive(state, run.id, () =>
        live.phase === "thinking"
          ? phased(live, "starting", now, {
              thoughtMs: live.thoughtMs === null ? null : live.thoughtMs + (now - live.since),
            })
          : { ...live, at: now },
      );
    default:
      return state;
  }
}

/**
 * The state as a connection is welcomed again: every running run's live output starts over, as
 * the server replays what it has of each, so nothing streamed shows twice; and a run the server
 * says is running that the store doesn't hold yet, as before the replay reaches its start or
 * when the store joins at the head, is held from here, so its frames aren't dropped. What a
 * thinking part took before the welcome isn't known any more.
 */
export function applyWelcome(state: Workspace, frame: v1.Server, now = Date.now()): Workspace {
  const active = frame.type === "welcome" ? (frame.active_runs ?? []) : [];
  const seeded = active.reduce(
    (next, run) => withRun(next, run.run_id, { threadId: run.thread_id, status: "running" }),
    state,
  );
  return Object.values(seeded.runs).reduce(
    (next, run) =>
      run.status === "running"
        ? withRun(next, run.id, { text: "", live: fresh(now, { thoughtMs: null }) })
        : next,
    seeded,
  );
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
    default:
      // A run's live frames; presence, which only a canvas's own connection asks for (portalr
      // ADR-0078); and any frame a later server adds, which an older app passes over.
      return { kind: "other", frame };
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
  other: (state, frame) => applyLive(state, frame, Date.now()),
  welcome: (state, frame) => applyWelcome(state, frame),
  creates: (command) => createdId(command) != null,
};

/** A store over an artifactr workspace's stream. */
export type ArtifactrStream = Stream<Workspace, v1.Server, v1.Command, v1.CommandResult, v1.Hello>;
