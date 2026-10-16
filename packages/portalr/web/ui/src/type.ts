/**
 * The kit's type scale, one place, so a page's title, a section's, a label, a line of prose and a
 * figure are the same wherever they are (portalr ADR-0039). Weights stop at 600: the face's 700 is
 * heavy beside Fragment Mono and the quiet text, and the size, not the weight, says what is the
 * title. Each is Tailwind's classes; a component takes the entry for what it is.
 */
export const TYPE = {
  /** A page's one heading. */
  page: "font-semibold text-2xl text-fg tracking-tight",
  /** A section's heading, under the page's. */
  section: "font-semibold text-fg text-lg tracking-tight",
  /** A label over a field, or the title of a card. */
  label: "font-semibold text-fg text-sm",
  /** Prose, and what a table holds. */
  body: "text-fg text-sm",
  /** A line about what is shown, under a title. */
  meta: "text-muted text-sm",
  /** A hint, a count, a time: the smallest. */
  note: "text-muted text-xs",
  /** A figure read on its own, such as a card's. */
  figure: "font-semibold text-2xl text-fg tracking-tight",
} as const;
