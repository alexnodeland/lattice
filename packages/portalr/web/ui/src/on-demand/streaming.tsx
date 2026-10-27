/**
 * What a turn under way says beyond its words (portalr ADR-0083), loaded as the first run
 * streams: what the model is doing, the one status that says so, the turn's token count,
 * estimated, and how long it thought. It imports nothing the chat doesn't hold already, so the
 * bundle shares no chunk between them.
 */

import type { Artifactr } from "@portalr/client";
import { useEffect, useState } from "react";

/** How long without a frame before the strip says the model is being waited on. */
const IDLE_MS = 20_000;

/** How often, at most, the phase is announced. */
const SAY_EVERY_MS = 3000;

/** A size in kilobytes, as a line says it: "0.8 KB", "12 KB". */
const kb = (chars: number) =>
  `${chars < 10_000 ? (chars / 1000).toFixed(1) : Math.round(chars / 1000)} KB`;

/** What a running turn is doing, in words. */
function doing({ phase, tool, calls, argsChars }: Artifactr.Live): string {
  switch (phase) {
    case "thinking":
      return "Thinking";
    case "writing":
      return "Writing the reply";
    case "tool":
      if (calls > 0) {
        return `Running ${tool ?? "a tool"}${calls > 1 ? ` and ${calls - 1} more` : ""}`;
      }
      return `Preparing a ${tool ? `${tool} ` : ""}call${argsChars > 0 ? `, ${kb(argsChars)}` : ""}`;
    default:
      return "Waiting on the model";
  }
}

/**
 * `words` as a status says them: on a change, at once if the last was said a while ago, and
 * otherwise once that while has passed, so a model that goes through phases in a blink isn't
 * announced at every one.
 */
function useSaid(words: string): string {
  const [said, setSaid] = useState({ words, at: Date.now() });
  useEffect(() => {
    if (words === said.words) {
      return;
    }
    const wait = Math.max(0, said.at + SAY_EVERY_MS - Date.now());
    const timer = setTimeout(() => setSaid({ words, at: Date.now() }), wait);
    return () => clearTimeout(timer);
  }, [words, said]);
  return said.words;
}

const count = (n: number) => n.toLocaleString();

/** The seconds since the run's last frame, or 0 before any. */
const idle = (live: Artifactr.Live, now: Date) =>
  live.at > 0 ? Math.floor((now.getTime() - live.at) / 1000) : 0;

/** How the run goes and what it is doing, as the strip's one status says it. */
export function Said({ run, status, now }: { run: Artifactr.Run; status: string; now: Date }) {
  const waiting = idle(run.live, now) * 1000 >= IDLE_MS;
  return useSaid(`${status}: ${doing(run.live)}${waiting ? ", nothing for a while" : ""}`);
}

/**
 * What a running turn is doing, in the strip's line, with how long since the last frame once
 * that is a while. Never announced: `Said` announces the phase.
 */
export function Phase({ run, now }: { run: Artifactr.Run; now: Date }) {
  const since = idle(run.live, now);
  return (
    <span>
      {doing(run.live)}
      {since * 1000 >= IDLE_MS && `, ${since} s since the last output`}
    </span>
  );
}

/** One count, as a chip: "in ~1,060", named in full for a screen reader. */
function Chip({ short, name, n }: { short: string; name: string; n: number }) {
  return (
    <span className="inline-flex items-center whitespace-nowrap rounded-(--badge-radius) bg-subtle px-(--badge-pad-end) py-(--badge-pad-y) font-medium text-muted text-xs tabular-nums">
      <span aria-hidden="true">
        {short} ~{count(n)}
      </span>
      <span className="sr-only">
        {name}, estimated: {count(n)}
      </span>
    </span>
  );
}

/**
 * The turn's tokens, as chips in the strip, estimated from the characters sent and streamed
 * (exact counts are a later phase's), "~" and their names saying so; never announced, as they
 * change with every frame. What was sent counts the thread's messages alone, so it is a floor.
 */
export function Tokens({
  run,
  history,
}: {
  run: Artifactr.Run;
  /** The characters of the thread's history the turn was sent, or null where that isn't known. */
  history: number | null;
}) {
  return (
    <span className="flex flex-wrap gap-1">
      {history !== null && <Chip short="in" name="Input tokens" n={Math.ceil(history / 4)} />}
      <Chip short="out" name="Output tokens" n={Math.ceil(run.live.outputChars / 4)} />
    </span>
  );
}

/**
 * What the thinking's disclosure says: "Thinking…" while it thinks; once it has, for how long, "a
 * moment" under a second, counting a part still open as the turn ended up to its last frame;
 * or "Thought" alone, where a reconnect lost its length.
 */
export function Thought({
  live,
  ended,
}: {
  live: Artifactr.Live;
  /** How the turn ended, if it has. */
  ended: "failed" | "stopped" | undefined;
}) {
  const thinking = live.phase === "thinking";
  if (thinking && !ended) {
    return "Thinking…";
  }
  if (live.thoughtMs === null) {
    return "Thought";
  }
  const ms = live.thoughtMs + (thinking ? live.at - live.since : 0);
  return `Thought for ${ms < 1000 ? "a moment" : `${Math.round(ms / 1000)} s`}`;
}
