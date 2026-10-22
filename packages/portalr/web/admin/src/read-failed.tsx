/**
 * What a screen of admin shows when its read failed, in the tenant's frame: its heading, then the
 * kit's `ErrorState`, reading it again, and any other way on, such as clearing a filter.
 */

import { ErrorState } from "@portalr/ui";
import { type ErrorComponentProps, useRouter } from "@tanstack/react-router";
import type { ReactNode } from "react";

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
      <ErrorState
        title={title}
        error={error}
        retry={() => {
          reset();
          void router.invalidate();
        }}
        action={children}
      />
    </>
  );
}
