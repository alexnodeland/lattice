import type { ComponentProps } from "react";
import { cn } from "./cn";
import { TYPE } from "./type";

/** The looks a heading below the page's may take, from the kit's type scale. */
const LOOK = {
  /** A section of a page: `SectionTitle`'s. */
  section: TYPE.section,
  /** A part of a section, or a pane beside the main one. */
  subsection: TYPE.subsection,
  /** A card's or a group's title. */
  label: TYPE.label,
  /** A card's title over the figure it names. */
  labelQuiet: TYPE.labelQuiet,
} as const;

type Level = 2 | 3 | 4;

/**
 * A heading below the page's one, at the level the outline needs and in one of the kit's looks
 * (portalr ADR-0062): the level says where it sits, the look how much it weighs, so a card's
 * title can be an `h3` and still look like a label. A heading that a form or a pane focuses
 * takes `tabIndex={-1}` and draws no ring.
 */
export function Heading({
  level,
  look,
  className,
  ...props
}: Omit<ComponentProps<"h2">, "className"> & {
  level: Level;
  look: keyof typeof LOOK;
  /** Layout only, such as breaking a long word: never the heading's type. */
  className?: string;
}) {
  const Tag = `h${level}` as const;
  return <Tag className={cn(LOOK[look], "outline-none", className)} {...props} />;
}
