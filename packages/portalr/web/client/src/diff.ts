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
 * How far jsdiff looks before it gives up: an edit of more than this many words or lines is too
 * large to compare (portalr ADR-0017). Bounded by size alone, never by time, so the same versions
 * are compared alike on every machine (portalr ADR-0054).
 */
export const BOUND = { maxEditLength: 2000 } as const;

/** The longest text compared, in characters: either version longer is too large to compare. */
export const LONGEST = 200_000;

/** The changes that make `after` from `before`, in order; null if they are too large to find. */
export function changes(before: string, after: string, by: Granularity): Change[] | null {
  if (before.length > LONGEST || after.length > LONGEST) {
    return null;
  }
  const parts = by === "words" ? diffWords(before, after, BOUND) : diffLines(before, after, BOUND);
  if (parts === undefined) {
    return null;
  }
  return parts.map((part) => ({
    kind: part.added ? "added" : part.removed ? "removed" : "same",
    text: part.value,
  }));
}
