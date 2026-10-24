/**
 * A tool a page reads from that didn't answer, said as a reader can act on it (issue 214): which
 * tool, and to try again, said politely as it appears, as a failure is. Why it didn't, the
 * server's words, is for operators: written to the console once for each reading, as the kit's
 * failures are, however often the page draws it.
 */

import { EmptyState, failureLogged } from "@portalr/ui";
import { useEffect } from "react";

/** A reading that didn't answer: its reason, the server's. */
interface Unread {
  readonly reason: string;
}

/** Each reading's failure, made once, so the console has it once. */
const failures = new WeakMap<Unread, Error>();

function failureOf(tool: string, reading: Unread): Error {
  let failure = failures.get(reading);
  if (failure === undefined) {
    failure = new Error(`${tool}: ${reading.reason}`);
    failures.set(reading, failure);
  }
  return failure;
}

/** What the reader is told, whatever the server said. */
const told = (tool: string) =>
  `The page couldn't read from ${tool} just now. Try again in a moment; if it goes on, tell whoever runs this deployment.`;

export function Unanswered({ tool, reading }: { tool: string; reading: Unread }) {
  useEffect(() => failureLogged(failureOf(tool, reading)), [tool, reading]);
  return (
    <div role="status">
      <EmptyState title={`${tool} isn't answering`}>{told(tool)}</EmptyState>
    </div>
  );
}
