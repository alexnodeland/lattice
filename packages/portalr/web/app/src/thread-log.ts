/**
 * A thread as its chat shows it, oldest first: its messages, the artifacts it shows, its runs' tool
 * calls, the questions its runs asked through `ask_user` (artifactr ADR-0083), and the turns that
 * failed, each where the log has it. A run's calls in a row are one group.
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
  | { readonly kind: "artifact"; readonly seq: number; readonly artifact: Artifactr.Artifact };

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
 * artifacts made in it that it shows, where each was made.
 */
export function threadLog(
  thread: Artifactr.Thread,
  runs: Readonly<Record<string, Artifactr.Run>>,
  inline: readonly Artifactr.Artifact[] = [],
): Entry[] {
  const mine = Object.values(runs).filter((run) => run.threadId === thread.id);
  const entries: Entry[] = [
    ...thread.messages.map((message) => ({ kind: "message", seq: message.seq, message }) as const),
    ...inline.map((artifact) => ({ kind: "artifact", seq: artifact.seq, artifact }) as const),
    ...mine.flatMap((run) => {
      return [
        ...Object.entries(run.tools)
          .filter(([call, tool]) => shownAsCall(run, call, tool))
          .map(
            ([call, tool]) =>
              ({ kind: "tools", seq: tool.seq, run, tools: [[call, tool]] }) as const,
          ),
        ...run.questions.map(
          (question) => ({ kind: "question", seq: question.seq, run, question }) as const,
        ),
        ...(run.status === "failed" && run.ended !== null
          ? [{ kind: "failed", seq: run.ended, run } as const]
          : []),
      ];
    }),
  ];
  entries.sort((a, b) => a.seq - b.seq);
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
export interface Retry {
  /** The failed run, whose notice offers it. */
  readonly run: string;
  /** Derived from the run, so a second try, from here or another tab, is the same message. */
  readonly id: string;
  readonly content: string;
}

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
  // every such id is someone else's offers no try, rather than looking for ever.
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
  return null;
}
