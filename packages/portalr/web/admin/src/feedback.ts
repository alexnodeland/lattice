/**
 * Feedback's window and workspace, as its address keeps them: portalr sums the scores in the
 * window by day, so the window is whole days, the same all day (portalr ADR-0027).
 */

import { type Days, daysOf } from "./window";

/** What Feedback's address keeps: the window, in days, and the workspace, if one is chosen. */
export type Shown = {
  /** Always given by `shownOf`; optional for a link, which may leave it out. */
  readonly days?: Days;
  readonly workspace?: string | undefined;
};

/**
 * The address's window and workspace: a window Feedback doesn't offer is its default, and a
 * workspace that isn't text is none, so the router doesn't keep what the address gave.
 */
export function shownOf(search: Record<string, unknown>): Required<Shown> {
  const days = daysOf(search.days);
  const workspace = typeof search.workspace === "string" ? search.workspace.trim() : "";
  return { days, workspace: workspace === "" ? undefined : workspace };
}

/**
 * How many of a summary's first days its read didn't reach: those before `known_from`, which
 * are unknown, not empty; every day, where it is after them all.
 */
export function unknownDays(summary: {
  readonly days: readonly { readonly day: string }[];
  readonly known_from?: string | null;
}): number {
  const from = summary.known_from;
  if (!from) {
    return 0;
  }
  const at = summary.days.findIndex((one) => one.day >= from);
  return at === -1 ? summary.days.length : at;
}
