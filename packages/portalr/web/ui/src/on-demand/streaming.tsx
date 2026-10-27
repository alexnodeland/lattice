/**
 * What a turn under way says beyond its words (portalr ADR-0083), loaded as the first run
 * streams: what the model is doing, the one status that says so, and the turn's token count,
 * estimated until exact. It imports nothing the chat doesn't hold already, so the bundle shares
 * no chunk between them.
 */

import type { Artifactr } from "@portalr/client";
import { useEffect, useState } from "react";
import type { Usage } from "../chat";
import { cn } from "../cn";
import { TYPE } from "../type";

/** How long without a frame before the strip says the model is being waited on. */
const IDLE_MS = 20_000;

/** How often, at most, the phase is announced. */
const SAY_EVERY_MS = 3000;

/** A size in kilobytes, as a line says it: "0.8 KB", "12 KB". */
const kb = (chars: number) =>
  `${chars < 10_000 ? (chars / 1000).toFixed(1) : Math.round(chars / 1000)} KB`;

/** What a running turn is doing, in words. */
function doing({ phase, tool, running, argsChars }: Artifactr.Live): string {
  switch (phase) {
    case "thinking":
      return "Thinking";
    case "writing":
      return "Writing the reply";
    case "tool":
      return running
        ? `Running ${tool}`
        : `Preparing ${tool} call${argsChars > 0 ? `, ${kb(argsChars)}` : ""}`;
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

/** How the run goes and what it is doing, as the strip's one status says it. */
export function Said({ run, status, now }: { run: Artifactr.Run; status: string; now: Date }) {
  const waiting = idle(run.live, now) * 1000 >= IDLE_MS;
  return useSaid(`${status}: ${doing(run.live)}${waiting ? ", nothing for a while" : ""}`);
}

/** The seconds since the run's last frame, or 0 before any. */
const idle = (live: Artifactr.Live, now: Date) =>
  live.at > 0 ? Math.floor((now.getTime() - live.at) / 1000) : 0;

/**
 * What a running turn is doing, in the strip: the line that says it, with how long since the
 * last frame once that is a while; and the turn's tokens, a quiet line of its own, estimated
 * from the characters sent and streamed until `usage` says exactly. Neither is announced: the
 * tokens change with every frame, and `Said` announces the phase.
 */
export function Doing({
  run,
  now,
  history,
  usage,
}: {
  run: Artifactr.Run;
  now: Date;
  /** The characters of the thread's history the turn was sent, or null where that isn't known. */
  history: number | null;
  usage: Usage | null;
}) {
  const { live } = run;
  const since = idle(live, now);
  const tokens = usage
    ? [
        `${count(usage.input)} in`,
        `${count(usage.output)} out`,
        ...(usage.cacheRead ? [`${count(usage.cacheRead)} from cache`] : []),
        ...(usage.reasoning ? [`${count(usage.reasoning)} thinking`] : []),
      ].join(", ")
    : `${history === null ? "" : `about ${count(Math.ceil(history / 4))} in, `}about ${count(
        Math.ceil(live.outputChars / 4),
      )} out, estimated`;
  return (
    <>
      <span className={TYPE.note}>
        {doing(live)}
        {since * 1000 >= IDLE_MS && `, ${since} s since the last output`}
      </span>
      {(history !== null || live.outputChars > 0) && (
        <span className={cn(TYPE.note, "order-1 basis-full tabular-nums")}>Tokens: {tokens}</span>
      )}
    </>
  );
}
