import type { ReactNode } from "react";
import { Alert } from "./alert";
import { Button } from "./button";
import { EmptyState } from "./empty-state";
import { failureSaid } from "./failure";

/**
 * A read that failed, where its content would be (portalr ADR-0065): a heading saying what
 * couldn't be read, the failure in the server's words, and one way on, reading it again. It
 * takes the focus, as a state that replaces the page does. `action` is for a second way on that
 * a screen has, such as clearing a filter.
 */
export function ErrorState({
  title,
  error,
  retry,
  action,
}: {
  /** What couldn't be read, such as "The audit log couldn't be read". */
  title: string;
  error: unknown;
  /** Read it again. Without it, `action` is the way on. */
  retry?: () => void;
  action?: ReactNode;
}) {
  return (
    <EmptyState
      focus
      title={title}
      action={
        (retry || action) && (
          <div className="flex flex-wrap gap-2">
            {retry && (
              <Button variant="secondary" onClick={retry}>
                Try again
              </Button>
            )}
            {action}
          </div>
        )
      }
    >
      <Alert tone="error">{failureSaid(error)}</Alert>
    </EmptyState>
  );
}
