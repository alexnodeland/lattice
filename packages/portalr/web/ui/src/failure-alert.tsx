import { useEffect } from "react";
import { Alert } from "./alert";
import { failureLogged, failureSaid } from "./failure";

/**
 * A failure, as a reader sees it: what didn't happen, if given, then the kit's sentence for it, in
 * an error alert. The whole failure goes to the console for operators, once, after the render.
 */
export function FailureAlert({ error, lead }: { error: unknown; lead?: string }) {
  useEffect(() => failureLogged(error), [error]);
  return (
    <Alert tone="error">
      {lead === undefined ? failureSaid(error) : `${lead} ${failureSaid(error)}`}
    </Alert>
  );
}
