/**
 * What changed between two versions of an artifact's text, by word or by line, as jsdiff finds it
 * (portalr ADR-0017). `ui` renders the changes; an artifact kind's renderer says how to cut them.
 */

import { diffLines, diffWords } from "diff";

/** How finely a kind's changes are cut: prose by word, structured text by line. */
export type Granularity = "words" | "lines";

/** One run of the text: kept, added in the later version, or removed from the earlier. */
export interface Change {
  readonly kind: "same" | "added" | "removed";
  readonly text: string;
}

/**
 * How far jsdiff looks before it gives up: an edit of more than this many words or lines, or a
 * comparison of more than this many milliseconds, is too large to compare (portalr ADR-0017).
 */
export const BOUND = { maxEditLength: 2000, timeout: 200 } as const;

/** The changes that make `after` from `before`, in order; null if they are too large to find. */
export function changes(before: string, after: string, by: Granularity): Change[] | null {
  const parts = by === "words" ? diffWords(before, after, BOUND) : diffLines(before, after, BOUND);
  if (parts === undefined) {
    return null;
  }
  return parts.map((part) => ({
    kind: part.added ? "added" : part.removed ? "removed" : "same",
    text: part.value,
  }));
}
