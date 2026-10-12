import type { ReactNode } from "react";
import { cn } from "./cn";

/**
 * A table of rows, named by its caption, on the surface, scrolling sideways rather than
 * squeezing on a narrow screen. Its rows are the caller's `<thead>` and `<tbody>`.
 */
export function Table({
  caption,
  children,
  className,
}: {
  /** What the table holds, read by assistive technology. */
  caption: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table
        className={cn(
          "w-full border-collapse text-fg text-sm [&_td]:border-line [&_td]:border-t [&_td]:px-3 [&_td]:py-2 [&_td]:align-middle [&_th]:whitespace-nowrap [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-semibold [&_th]:text-muted [&_th]:text-xs [&_tbody_tr:hover]:bg-wash",
          className,
        )}
      >
        <caption className="sr-only">{caption}</caption>
        {children}
      </table>
    </div>
  );
}
