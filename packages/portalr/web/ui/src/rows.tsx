import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import type { ComponentProps, ReactElement, ReactNode } from "react";
import { cn } from "./cn";

/** A list of rows, lined one under another, named for what they are. */
export function Rows({ label, children }: { label: string; children: ReactNode }) {
  return (
    <ul aria-label={label} className="flex flex-col divide-y divide-line border-line border-y">
      {children}
    </ul>
  );
}

/**
 * One row (portalr ADR-0060): what it is, on its first line, then what is said about it, quieter, on
 * its second, and at its end what it is doing or what can be done to it. Its `RowLink`, if its
 * title is one, is the whole row's target; what is at its end stays its own target, above it.
 */
export function Row({
  title,
  meta,
  end,
  ...props
}: Omit<ComponentProps<"li">, "className" | "title" | "children"> & {
  title: ReactNode;
  meta?: ReactNode;
  end?: ReactNode;
}) {
  return (
    <li
      className="relative grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-(--list-row-gap) px-(--list-row-pad-x) py-(--list-row-pad-y) text-sm has-[a:hover]:bg-wash has-[a:focus-visible]:bg-wash"
      {...props}
    >
      <div className="flex min-w-0 flex-col gap-(--list-row-line-gap)">
        <span className="min-w-0 truncate">{title}</span>
        {meta && <span className="min-w-0 truncate text-muted">{meta}</span>}
      </div>
      {end && (
        <div className="relative z-10 flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
          {end}
        </div>
      )}
    </li>
  );
}

type RowLinkProps = Omit<ComponentProps<"a">, "className"> & {
  /** What to render as the link, such as the router's own. */
  render?: ReactElement;
  className?: string;
};

/** A row's link, stretched over the row, so the whole row takes the pointer. */
export function RowLink({ render, className, ...props }: RowLinkProps) {
  return useRender({
    defaultTagName: "a",
    render,
    props: mergeProps<"a">(
      {
        className: cn(
          "font-semibold text-fg underline-offset-(--link-underline-offset) outline-none after:absolute hover:text-accent hover:underline after:inset-0 after:content-[''] focus-visible:after:outline-(length:--focus-width) focus-visible:after:outline-focus focus-visible:after:-outline-offset-(--focus-offset)",
          className,
        ),
      },
      props,
    ),
  });
}
