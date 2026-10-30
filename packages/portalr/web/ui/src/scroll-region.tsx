import type { ReactNode } from "react";
import { cn } from "./cn";

/** A scrolling region's look: a tab stop, with the focus ring the kit's controls have. */
export const SCROLLS =
  "overflow-x-auto outline-offset-(--focus-offset) focus-visible:outline-(length:--focus-width) focus-visible:outline-focus phone:as-scroll-shadows";

/**
 * A long list's own scroll box, as a log's records and a trace's spans are: up to 30rem tall, on
 * the surface, in a card's corners and hairline, never less than a few rows.
 */
export const SCROLL_BOX =
  "max-h-120 min-h-24 overflow-auto rounded-(--card-radius) border border-line bg-surface";

/**
 * What scrolls sideways when it is wider than the page, such as a table or a block of code: a tab
 * stop, so a keyboard can scroll it as a pointer can, and a named region, so a reader can find it
 * (WCAG 2.1.1). Name it with a label, or the id of the heading that names it.
 */
export function ScrollRegion({
  className,
  children,
  ...naming
}: ({ "aria-label": string } | { "aria-labelledby": string }) & {
  className?: string | undefined;
  children: ReactNode;
}) {
  return (
    <section {...naming} tabIndex={0} className={cn(SCROLLS, className)}>
      {children}
    </section>
  );
}
