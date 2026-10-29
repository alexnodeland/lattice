/**
 * A thread as its chat shows it, oldest first: its messages, the artifacts it shows, its runs' tool
 * calls, the questions its runs asked through `ask_user` (artifactr ADR-0083), and the turns that
 * failed, or were stopped, with what they had streamed, each where the log has it. A run's calls
 * in a row are one group; a mini app updated by one is shown again beneath it (portalr ADR-0055).
 * A proposal that was decided is a line after its run's last entry (portalr ADR-0092).
 */

import type { Artifactr } from "@portalr/client";

export type Entry =
  | { readonly kind: "message"; readonly seq: number; readonly message: Artifactr.Message }
  | {
      readonly kind: "tools";
      readonly seq: number;
      readonly run: Artifactr.Run;
      readonly tools: readonly (readonly [string, Artifactr.Tool])[];
    }
  | {
      readonly kind: "question";
      readonly seq: number;
      readonly run: Artifactr.Run;
      readonly question: Artifactr.Question;
    }
  | { readonly kind: "failed"; readonly seq: number; readonly run: Artifactr.Run }
  | {
      readonly kind: "proposal";
      readonly seq: number;
      /** One that was accepted or rejected. */
      readonly proposal: Artifactr.Proposal;
    }
  /** What a run that failed, or was stopped, had streamed before it ended; a stop itself (portalr ADR-0083). */
  | {
      readonly kind: "partial";
      readonly seq: number;
      readonly run: Artifactr.Run & { readonly status: "failed" | "stopped" };
    }
  | {
      readonly kind: "artifact";
      readonly seq: number;
      readonly artifact: Artifactr.Artifact;
      /** The `update_app` call it is shown under, again, at its latest version. */
      readonly updatedBy?: string;
      /** The version that call made. */
      readonly version?: number;
      /**
       * Set on an app's card that a later one in the thread follows: the version it made, shown
       * without running, so only the app's newest card runs it.
       */
      readonly superseded?: number;
    };

/**
 * What `update_app` returns once the app is at its next version: artifactr's `describe_outcome`
 * (agent/tools.py), as the run records it, cut by `_clip` (agent/capability.py) past its limit, so
 * a result cut short matches nothing and is a call alone. Change them together.
 */
const APPLIED = /^Done: (\S+) is now at version (\d+)\.$/;

/** The app an `update_app` call updated, and the version it made, once it did; else null. */
function appUpdated(
  tool: Artifactr.Tool,
  artifacts: Readonly<Record<string, Artifactr.Artifact>>,
): readonly [Artifactr.Artifact, number] | null {
  const [, id = "", version] =
    (tool.status === "ok" && tool.name === "update_app" && APPLIED.exec(tool.result)) || [];
  const artifact = artifacts[id];
  return artifact?.kind === "app" ? [artifact, Number(version)] : null;
}

/**
 * A run that ended before its reply, with what it had streamed, its words or its thinking; a
 * stopped one is shown even with none, as the thread says it stopped there.
 */
function unfinished(
  run: Artifactr.Run,
): run is Artifactr.Run & { readonly status: "failed" | "stopped" } {
  return (
    run.status === "stopped" ||
    (run.status === "failed" && (run.text !== "" || run.live.thinking !== ""))
  );
}

/**
 * Whether a run's call is shown as a call: one that asked questions is shown as its questions, and
 * one still open once its run paused or ended, as a form's call is, isn't running.
 */
function shownAsCall(run: Artifactr.Run, call: string, tool: Artifactr.Tool): boolean {
  const questioned = run.questions.some(({ request }) => request.tool_call_id === call);
  return !questioned && (tool.status !== "called" || run.status === "running");
}

/**
 * A thread's entries, in the log's order, of its messages, the runs in it, and `inline`: the
 * artifacts made in it that it shows, where each was made. A call that updated a mini app, of the
 * workspace's `artifacts`, has the app again beneath it, at its latest version. Each of the
 * `decided` proposals, which carry no place of their own, follows the last entry of the run that
 * made it, and the thread's last where no run did.
 */
export function threadLog(
  thread: Artifactr.Thread,
  runs: Readonly<Record<string, Artifactr.Run>>,
  inline: readonly Artifactr.Artifact[] = [],
  artifacts: Readonly<Record<string, Artifactr.Artifact>> = {},
  decided: readonly Artifactr.Proposal[] = [],
): Entry[] {
  const mine = Object.values(runs).filter((run) => run.threadId === thread.id);
  // Each call, and, beneath one that updated an app, the app again, as where it was made.
  const shown = mine.flatMap((run) =>
    Object.entries(run.tools)
      .filter(([id, tool]) => shownAsCall(run, id, tool))
      .flatMap(([id, tool]): Entry[] => {
        const updated = appUpdated(tool, artifacts);
        const entry: Entry = { kind: "tools", seq: tool.seq, run, tools: [[id, tool]] };
        if (updated === null) {
          return [entry];
        }
        const [artifact, version] = updated;
        return [entry, { kind: "artifact", seq: tool.seq, artifact, updatedBy: id, version }];
      }),
  );
  const entries: Entry[] = [
    ...thread.messages.map((message) => ({ kind: "message", seq: message.seq, message }) as const),
    ...inline.map((artifact) => ({ kind: "artifact", seq: artifact.seq, artifact }) as const),
    ...shown,
    ...mine.flatMap((run) => {
      return [
        ...run.questions.map(
          (question) => ({ kind: "question", seq: question.seq, run, question }) as const,
        ),
        // What it streamed comes before why it failed, at the same place.
        ...(unfinished(run) && run.ended !== null
          ? [{ kind: "partial", seq: run.ended, run } as const]
          : []),
        ...(run.status === "failed" && run.ended !== null
          ? [{ kind: "failed", seq: run.ended, run } as const]
          : []),
      ];
    }),
  ];
  entries.sort((a, b) => a.seq - b.seq);
  // The last place of each run, which a proposal it made follows, half a place on.
  const last = new Map<string, number>();
  for (const entry of entries) {
    const run =
      entry.kind === "message" ? entry.message.runId : "run" in entry ? entry.run.id : null;
    if (run !== null) {
      last.set(run, entry.seq);
    }
  }
  for (const proposal of decided) {
    const after = last.get(proposal.runId ?? "") ?? Number.MAX_SAFE_INTEGER;
    entries.push({ kind: "proposal", seq: after + 0.5, proposal });
  }
  entries.sort((a, b) => a.seq - b.seq);
  // An app runs in its newest card alone; each before it shows the version it made, or its first.
  const newest = new Map(
    entries.flatMap((entry, at) =>
      entry.kind === "artifact" && entry.artifact.kind === "app" ? [[entry.artifact.id, at]] : [],
    ),
  );
  entries.forEach((entry, at) => {
    if (
      entry.kind === "artifact" &&
      entry.artifact.kind === "app" &&
      newest.get(entry.artifact.id) !== at
    ) {
      entries[at] = { ...entry, superseded: entry.version ?? 1 };
    }
  });
  // A run's calls in a row, with nothing of the thread's between them, are one group.
  return entries.reduce<Entry[]>((grouped, entry) => {
    const last = grouped.at(-1);
    if (entry.kind === "tools" && last?.kind === "tools" && last.run.id === entry.run.id) {
      grouped[grouped.length - 1] = { ...last, tools: [...last.tools, ...entry.tools] };
    } else {
      grouped.push(entry);
    }
    return grouped;
  }, []);
}

/** A failed turn tried again: the messages that started it, posted again as one under `id`. */
export type Retry =
  | {
      /** The failed run, whose notice offers it. */
      readonly run: string;
      /** Derived from the run, so a second try, from here or another tab, is the same message. */
      readonly id: string;
      readonly content: string;
    }
  | {
      readonly run: string;
      /** Every id a try may take is someone else's message's: it can't be offered. */
      readonly id: null;
    };

/** Why a failed turn offers no try again, when every id one may take is someone else's. */
export const RETRY_TAKEN =
  "It can't be tried again here: other messages hold the ids a try would use. Send it again as a new message.";

/** The most ids a try again looks through for one no one else's message has. */
const TRIES = 100;

/**
 * What "Try again" sends for the thread's latest turn, if it failed and the reader started it:
 * the messages that started it, in order, posted again as one, under an id derived from the run,
 * which the server takes once. If another message already has that id, the next one is used, so
 * no one can take the try away by posting under its id first.
 * Null if the latest turn didn't fail, someone else started it, or it was tried again.
 */
export function retryOf(
  thread: Artifactr.Thread,
  runs: Readonly<Record<string, Artifactr.Run>>,
  me: string,
): Retry | null {
  const latest = Object.values(runs)
    .filter((run) => run.threadId === thread.id)
    .sort((a, b) => b.started - a.started)[0];
  if (latest?.status !== "failed") {
    return null;
  }
  const byId = new Map(thread.messages.map((message) => [message.id, message]));
  const started = latest.prompt.flatMap((id) => byId.get(id) ?? []);
  const mine = (message: Artifactr.Message) =>
    message.actor.kind === "user" && message.actor.id === me;
  if (started.length === 0 || !started.every(mine)) {
    return null;
  }
  const content = started.map((message) => message.content).join("\n\n");
  // The first of `msg_again_<run>`, `…_2`, `…_3` that no one else's message has: the same from
  // render to render and tab to tab, so every try is the one message. Bounded: a thread whose
  // every such id is someone else's says so, rather than looking for ever.
  for (let n = 1; n <= TRIES; n++) {
    const id = n === 1 ? `msg_again_${latest.id}` : `msg_again_${latest.id}_${n}`;
    const taken = byId.get(id);
    if (taken === undefined) {
      return { run: latest.id, id, content };
    }
    if (mine(taken) && taken.content === content) {
      return null; // tried again already
    }
  }
  return { run: latest.id, id: null };
}
