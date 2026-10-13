import type { ReactNode } from "react";
import { cn } from "./cn";

/** How a table, or a list in its place, is named: by its caption, or by a heading's id. */
export type Name = { readonly caption: string } | { readonly by: string };

/**
 * A table of rows, named by its caption, or by a heading beside it, on the surface, scrolling sideways rather than
 * squeezing on a narrow screen: the scroll is a region of the same name the keyboard can reach.
 * Its rows are the caller's `<thead>` and `<tbody>`, whose header cells say what they head with
 * `scope="col"` or `scope="row"`: a column's header is small and muted; a row's header is in the
 * row's own type, between its borders. Biome's rule against a tabindex on a non-interactive element
 * is off for this file alone (biome.json): a scroll container is one the keyboard must reach.
 */
export function Table({
  name,
  children,
  className,
}: {
  /**
   * What the table holds: a caption read by assistive technology, or the id of a visible
   * heading that names it.
   */
  name: Name;
  children: ReactNode;
  className?: string;
}) {
  const named = nameOf(name);
  return (
    <section
      {...named}
      tabIndex={0}
      className="overflow-x-auto rounded-lg border border-line bg-surface outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus"
    >
      <table
        {...("by" in name && { "aria-labelledby": name.by })}
        className={cn(
          "w-full border-collapse text-fg text-sm [&_td]:border-line [&_td]:border-t [&_td]:px-3 [&_td]:py-2 [&_td]:align-middle [&_th]:whitespace-nowrap [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_thead_th]:font-semibold [&_thead_th]:text-muted [&_thead_th]:text-xs [&_tbody_th]:border-line [&_tbody_th]:border-t [&_tbody_th]:align-middle [&_tbody_th]:font-semibold [&_tbody_th]:text-fg [&_tbody_th]:text-sm [&_tbody_tr:hover]:bg-wash",
          className,
        )}
      >
        {"caption" in name && <caption className="sr-only">{name.caption}</caption>}
        {children}
      </table>
    </section>
  );
}

/** The attribute that names a table's region, or a list: its label, or what labels it. */
export const nameOf = (name: Name) =>
  "caption" in name ? { "aria-label": name.caption } : { "aria-labelledby": name.by };
