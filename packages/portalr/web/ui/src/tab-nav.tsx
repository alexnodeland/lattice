import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import type { ComponentProps, ReactElement, ReactNode } from "react";
import { cn } from "./cn";
import { FEEDBACK } from "./states";

/**
 * A row of links to an area's parts, named by `label`; the current part is marked. The row stays
 * one row: on a phone, it scrolls sideways rather than wrap a part onto a line of its own.
 */
export function TabNav({ label, children }: { label: string; children: ReactNode }) {
  return (
    <nav
      aria-label={label}
      className="mb-4 flex gap-1 overflow-x-auto border-line border-b [--scroll-cover:var(--paper)] phone:as-scroll-shadows"
    >
      {children}
    </nav>
  );
}

/**
 * One of a tab bar's links: a router's link, through `render`, which marks the current part with
 * `aria-current="page"`, underlined in the working colour.
 */
// A tab's outline is drawn inside it (-outline-offset-(--focus-offset)): the row scrolls, so it clips what is
// drawn outside it, and a ring outside the tab would be cut off at the row's edge.
export function TabLink({
  render,
  children,
  ...props
}: Omit<ComponentProps<"a">, "className"> & { render?: ReactElement; children: ReactNode }) {
  return useRender({
    defaultTagName: "a",
    render,
    props: mergeProps<"a">(
      {
        className: cn(
          "-mb-px shrink-0 whitespace-nowrap border-transparent border-b-(length:--tabs-indicator) px-(--tabs-pad-x) py-(--tabs-pad-y) font-medium text-muted text-sm -outline-offset-(--focus-offset) hover:text-fg focus-visible:outline-(length:--focus-width) focus-visible:outline-focus aria-[current=page]:border-accent aria-[current=page]:text-fg",
          FEEDBACK,
        ),
        children,
      },
      props,
    ),
  });
}
