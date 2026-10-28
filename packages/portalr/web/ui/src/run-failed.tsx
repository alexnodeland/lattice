/**
 * A turn that failed, in its thread: why, in words a reader can act on, what the run recorded,
 * and, for the thread's latest turn, a way to try again.
 */

import { Alert } from "./alert";
import { CommandButton } from "./chat";
import { Disclosure } from "./disclosure";
import type { Sent } from "./sending";

/** Why a run failed, in words, by the reason its `run_ended` names (artifactr ADR-0042). */
const REASONS: Readonly<Record<string, string>> = {
  tool_retries_exhausted:
    "The model kept calling a tool in a way the tool refused, and ran out of tries.",
  unexpected_model_behavior: "The model answered in a way the turn couldn't use.",
  abandoned: "The turn stopped answering, and was given up.",
  guardrail_blocked: "A guardrail stopped the turn.",
  model_stalled:
    "The model stopped answering, so the turn was ended. Your message is safe; send it again.",
  tool_stalled: "A tool didn't return, so the turn was ended. Your message is safe; send it again.",
};

/**
 * What a provider's error says, in words a reader can act on (portalr ADR-0070, ADR-0085): the
 * error itself stays under Details, never in the sentence.
 */
const SAID: readonly (readonly [RegExp, string])[] = [
  [/overloaded|\b529\b/i, "The model was overloaded, so it couldn't answer. Nothing was lost."],
  [
    /rate.?limit|\b429\b/i,
    "The model's provider is taking no more requests for a moment. Nothing was lost.",
  ],
  [/time(d)? ?out/i, "The model took too long to answer. Nothing was lost."],
];

/** Why it failed, in words: its reason's, else its error's, else the kit's sentence. */
const why = (reason: string | null, error: string | null) =>
  (reason !== null && REASONS[reason]) ||
  SAID.find(([pattern]) => error !== null && pattern.test(error))?.[1] ||
  "Something went wrong before it answered.";

/**
 * A failed turn: what went wrong, the run's own words under "Details" where `error` is given,
 * which the thread gives the person the turn acted for, and "Try again" where `onRetry` is,
 * which it gives its latest turn, or `retryRefused`, why it can't. That one is announced, as it
 * fails, and any the thread says is (`live`); one further up is a note.
 */
export function RunFailed({
  reason,
  error,
  onRetry,
  retryRefused,
  live,
}: {
  reason: string | null;
  error: string | null;
  onRetry?: () => Sent;
  /** Why the latest turn can't be tried again, in place of "Try again". */
  retryRefused?: string;
  /** Announce it, as a thread does for a turn that fails while the page is open. */
  live?: boolean | undefined;
}) {
  return (
    <li className="self-stretch">
      <Alert tone="error" live={live ?? (onRetry !== undefined || retryRefused !== undefined)}>
        <div className="flex flex-col gap-2">
          <p>
            <span className="font-semibold">The assistant couldn't finish. </span>
            {why(reason, error)}
          </p>
          {error && (
            <Disclosure summary="Details" className="text-muted">
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-xs">
                {error}
              </pre>
            </Disclosure>
          )}
          {retryRefused && <p>{retryRefused}</p>}
          {onRetry && (
            <span>
              <CommandButton onSend={onRetry}>Try again</CommandButton>
            </span>
          )}
        </div>
      </Alert>
    </li>
  );
}
