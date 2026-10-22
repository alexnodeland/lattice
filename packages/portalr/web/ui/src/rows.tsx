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
 * One row (portalr ADR-0060): what it is, its `name`, first, then what is said about it, quieter,
 * beneath, each wrapping rather than cut, so nothing in a row is hidden; and at its end what it is
 * doing or what can be done to it, against the row's end, in a column no wider than half the row.
 * Where the row is narrow, its end goes under its meta, so a long end never squeezes its name. Its
 * `RowLink`, if its name is one, is the whole row's target; what is at its end stays its own
 * target, above it.
 */
export function Row({
  name,
  meta,
  end,
  ...props
}: Omit<ComponentProps<"li">, "className" | "children"> & {
  name: ReactNode;
  meta?: ReactNode;
  end?: ReactNode;
}) {
  return (
    <li
      className="relative grid grid-cols-1 items-center gap-x-(--list-row-gap) gap-y-(--list-row-line-gap) px-(--list-row-pad-x) py-(--list-row-pad-y) text-sm has-[a:hover]:bg-wash has-[a:focus-visible]:bg-wash sm:grid-cols-[minmax(0,1fr)_fit-content(50%)]"
      {...props}
    >
      <div className="flex min-w-0 flex-col gap-(--list-row-line-gap)">
        <div className="min-w-0 break-words">{name}</div>
        {meta && <div className="min-w-0 break-words text-muted">{meta}</div>}
      </div>
      {end && (
        <div className="relative z-10 flex flex-wrap items-center gap-x-3 gap-y-1 sm:justify-end">
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

/**
 * A row's link, stretched over the row, so the whole row takes the pointer: in the text's colour
 * with the quiet underline of a subtle link (ADR-0059), so it reads as a link on a touch screen too,
 * taking the working colour when hovered or reached from the keyboard.
 */
export function RowLink({ render, className, ...props }: RowLinkProps) {
  return useRender({
    defaultTagName: "a",
    render,
    props: mergeProps<"a">(
      {
        className: cn(
          "font-semibold text-fg underline decoration-edge underline-offset-(--link-underline-offset) outline-none after:absolute hover:text-accent hover:decoration-accent focus-visible:text-accent focus-visible:decoration-accent after:inset-0 after:content-[''] focus-visible:after:outline-(length:--focus-width) focus-visible:after:outline-focus focus-visible:after:-outline-offset-(--focus-offset)",
          className,
        ),
      },
      props,
    ),
  });
}
