/**
 * A tool a page reads from that didn't answer, said as a reader can act on it (issue 214): which tool,
 * and to try again. Why it didn't, the server's words, is for operators: written to the console,
 * once, as the kit's failures are.
 */

import { EmptyState, failureLogged } from "@portalr/ui";
import { useEffect } from "react";

export function Unanswered({ tool, reason }: { tool: string; reason: string }) {
  useEffect(() => failureLogged(new Error(`${tool}: ${reason}`)), [tool, reason]);
  return (
    <EmptyState title={`${tool} isn't answering`}>
      {`The page couldn't read from ${tool} just now. Try again in a moment; if it goes on, tell whoever runs this deployment.`}
    </EmptyState>
  );
}
