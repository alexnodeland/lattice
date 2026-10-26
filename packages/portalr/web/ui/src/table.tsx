import type { ReactNode } from "react";
import { cn } from "./cn";
import { ScrollRegion } from "./scroll-region";

/**
 * A table of rows, named by its caption or by a heading beside it, on the surface, scrolling
 * sideways rather than squeezing on a narrow screen: the scroll is a region of the same name the
 * keyboard can reach. Its rows are the caller's `<thead>` and `<tbody>`, whose header cells say
 * what they head with `scope="col"` or `scope="row"`: a column's header is small and muted, and a
 * row's is in the row's own type, between its borders.
 */
export function Table({
  children,
  className,
  ...naming
}: (
  | {
      /** What the table holds, read by assistive technology. */
      caption: string;
    }
  | {
      /** The id of the visible heading that names the table. */
      labelledBy: string;
    }
) & {
  children: ReactNode;
  className?: string | undefined;
}) {
  const caption = "caption" in naming ? naming.caption : undefined;
  const labelledBy = "labelledBy" in naming ? naming.labelledBy : undefined;
  return (
    <ScrollRegion
      {...("caption" in naming
        ? { "aria-label": naming.caption }
        : { "aria-labelledby": naming.labelledBy })}
      className="rounded-(--table-radius) border border-line bg-surface"
    >
      <table
        aria-labelledby={labelledBy}
        className={cn(
          "w-full border-collapse text-(length:--table-text) text-fg [&_td]:border-line [&_td]:border-t [&_td]:h-(--row-height) [&_td]:px-(--table-cell-pad-x) [&_td]:py-(--row-pad) [&_td]:align-middle [&_th]:h-(--row-height) [&_th]:whitespace-nowrap [&_th]:px-(--table-cell-pad-x) [&_th]:py-(--row-pad) [&_th]:text-left [&_thead_th]:font-semibold [&_thead_th]:text-muted [&_thead_th]:text-xs [&_tbody_th]:border-line [&_tbody_th]:border-t [&_tbody_th]:align-middle [&_tbody_th]:font-semibold [&_tbody_th]:text-fg [&_tbody_th]:text-(length:--table-text) [&_tbody_tr:hover]:bg-wash",
          // A row's wash follows the pointer as a nav link's does: `FEEDBACK`, on each row.
          "[&_tbody_tr]:transition-[color,background-color,border-color,text-decoration-color] [&_tbody_tr]:duration-(--feedback-duration) [&_tbody_tr]:ease-(--feedback-ease) [&_tbody_tr]:motion-reduce:transition-none",
          className,
        )}
      >
        {caption !== undefined && <caption className="sr-only">{caption}</caption>}
        {children}
      </table>
    </ScrollRegion>
  );
}
