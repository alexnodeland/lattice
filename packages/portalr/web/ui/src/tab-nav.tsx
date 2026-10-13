import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import type { ComponentProps, ReactElement, ReactNode } from "react";

/** A row of links to an area's parts, named by `label`; the current part is marked. */
export function TabNav({ label, children }: { label: string; children: ReactNode }) {
  return (
    <nav aria-label={label} className="mb-4 flex flex-wrap gap-1 border-line border-b">
      {children}
    </nav>
  );
}

/**
 * One of a tab bar's links: a router's link, through `render`, which marks the current part with
 * `aria-current="page"`, underlined in the working colour.
 */
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
        className:
          "-mb-px border-transparent border-b-2 px-3 py-2 font-medium text-muted text-sm outline-offset-2 hover:text-fg focus-visible:outline-2 focus-visible:outline-focus aria-[current=page]:border-accent aria-[current=page]:text-fg",
        children,
      },
      props,
    ),
  });
}
