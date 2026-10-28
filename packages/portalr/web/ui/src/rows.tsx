import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import type { ComponentProps, ReactElement, ReactNode } from "react";
import { cn } from "./cn";
import { Icon } from "./icon";
import { type Glyph, glyphs } from "./icons";
import { FEEDBACK, RING } from "./states";

/**
 * A list of rows (portalr ADR-0080): on the surface, bounded by a hairline with the table's
 * corners, the rows told apart by hairlines, named for what they are.
 */
export function Rows({ label, children }: { label: string; children: ReactNode }) {
  return (
    <ul
      aria-label={label}
      className="flex flex-col divide-y divide-line overflow-hidden rounded-(--table-radius) border border-line bg-surface"
    >
      {children}
    </ul>
  );
}

/**
 * One row (portalr ADR-0060, ADR-0080): what it is, its `name`, first, then what is said about it,
 * quieter, beneath, each wrapping rather than cut, so nothing in a row is hidden; and at its end
 * what it is doing or what can be done to it, against the row's end, in a column no wider than
 * half the row. Where the row is narrow, its end goes under its meta, so a long end never squeezes
 * its name. Its `RowLink`, if its name is one, is the whole row's target, which the kit's chevron
 * at the row's end says; what is at its end stays its own target, above it.
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
      className={cn(
        "group relative grid items-center gap-x-(--list-row-gap) gap-y-(--list-row-line-gap) px-(--list-row-pad-x) py-(--list-row-pad-y) text-sm has-[a:hover]:bg-subtle has-[a:focus-visible]:bg-subtle",
        // With something at its end, a narrow row stacks it under the meta; the chevron alone
        // keeps its column at every width, so it never wraps under the name.
        end
          ? "grid-cols-1 sm:grid-cols-[minmax(0,1fr)_fit-content(50%)]"
          : "grid-cols-[minmax(0,1fr)_auto]",
        FEEDBACK,
      )}
      {...props}
    >
      <div className="flex min-w-0 flex-col gap-(--list-row-line-gap)">
        <div className="min-w-0 break-words">{name}</div>
        {meta && <div className="min-w-0 break-words text-muted">{meta}</div>}
      </div>
      <div className="relative z-10 flex flex-wrap items-center gap-x-3 gap-y-1 sm:justify-end">
        {end}
        {/* Where the row's name is a link and nothing else is at its end, the chevron says it opens. */}
        {!end && (
          <Icon
            icon={glyphs.chevronRight}
            className="hidden text-muted group-has-[a]:block group-has-[a:hover]:text-accent"
          />
        )}
      </div>
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
 * and weight, with no underline (ADR-0080), the row's chevron saying it opens, and taking the
 * working colour when hovered or reached from the keyboard.
 */
export function RowLink({ render, className, ...props }: RowLinkProps) {
  return useRender({
    defaultTagName: "a",
    render,
    props: mergeProps<"a">(
      {
        className: cn(
          "font-semibold text-fg outline-none after:absolute hover:text-accent focus-visible:text-accent after:inset-0 after:content-[''] focus-visible:after:outline-(length:--focus-width) focus-visible:after:outline-focus focus-visible:after:-outline-offset-(--focus-offset)",
          FEEDBACK,
          className,
        ),
      },
      props,
    ),
  });
}

/**
 * A compact track of ways on, such as a workspace's areas (portalr ADR-0085): a segment's look,
 * flat on the quiet wash, each a link with its glyph and its word; on a phone the track is the
 * row's width, each cell its glyph over its word, a finger's 44px tall. It sits above a row's
 * stretched link, so each is its own target.
 */
export function Tracks({ label, children }: { label: string; children: ReactNode }) {
  return (
    <nav
      aria-label={label}
      data-track=""
      className="relative z-10 mt-1 inline-flex gap-0.5 self-start rounded-(--segmented-radius) border border-line bg-subtle p-(--segmented-pad) max-sm:flex max-sm:self-stretch"
    >
      {children}
    </nav>
  );
}

/** One of a track's links, the router's through `render`. */
export function TrackLink({
  render,
  icon,
  children,
}: {
  render: ReactElement;
  icon: Glyph;
  children: string;
}) {
  return useRender({
    defaultTagName: "a",
    render,
    props: {
      "aria-label": children,
      className: cn(
        "inline-flex min-w-0 items-center justify-center gap-1.5 rounded-(--segmented-item-radius) px-1 py-(--segmented-item-pad-y) font-medium text-muted text-sm hover:text-fg max-sm:flex-auto max-sm:flex-col",
        RING,
        FEEDBACK,
      ),
      children: (
        <>
          <Icon icon={icon} />
          <span aria-hidden="true" className="max-w-full truncate text-xs max-sm:text-[0.6875rem]">
            {children}
          </span>
        </>
      ),
    },
  });
}
