import type { ReactNode } from "react";
import { cn } from "./cn";

/** A scrolling region's look: a tab stop, with the focus ring the kit's controls have. */
export const SCROLLS =
  "overflow-x-auto outline-offset-(--focus-offset) focus-visible:outline-(length:--focus-width) focus-visible:outline-focus phone:as-scroll-shadows";

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
