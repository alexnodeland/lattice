/**
 * What a screen of admin shows when its read failed, in the tenant's frame: its heading, what
 * failed, a way to read it again, and any other way on, such as clearing a filter.
 */

import { Button, EmptyState } from "@portalr/ui";
import { type ErrorComponentProps, useRouter } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { failureSaid } from "./format";

export function ReadFailed({
  title,
  header,
  error,
  reset,
  children,
}: Pick<ErrorComponentProps, "error" | "reset"> & {
  /** What couldn't be read, such as "The audit log couldn't be read". */
  title: string;
  /** The screen's own heading, so the failure sits where the screen would. */
  header: ReactNode;
  /** Another way on, beside reading again. */
  children?: ReactNode;
}) {
  const router = useRouter();
  return (
    <>
      {header}
      <EmptyState
        title={title}
        action={
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                reset();
                void router.invalidate();
              }}
            >
              Try again
            </Button>
            {children}
          </div>
        }
      >
        <p role="alert">{failureSaid(error)}</p>
      </EmptyState>
    </>
  );
}
