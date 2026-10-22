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
};

/**
 * A failed turn: what went wrong, the run's own words under "Details" where `error` is given,
 * which the thread gives the person the turn acted for, and "Try again" where `onRetry` is, which
 * it gives its latest turn, or `retryRefused`, why it can't. Only that one is announced, as it fails; one further up is a note.
 */
export function RunFailed({
  reason,
  error,
  onRetry,
  retryRefused,
}: {
  reason: string | null;
  error: string | null;
  onRetry?: () => Sent;
  /** Why the latest turn can't be tried again, in place of "Try again". */
  retryRefused?: string;
}) {
  return (
    <li className="self-stretch">
      <Alert tone="error" live={onRetry !== undefined || retryRefused !== undefined}>
        <div className="flex flex-col gap-2">
          <p>
            <span className="font-semibold">The assistant couldn't finish. </span>
            {(reason !== null && REASONS[reason]) || "Something went wrong before it answered."}
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
