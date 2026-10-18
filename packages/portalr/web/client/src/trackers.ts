/**
 * What a workspace's runs filed in its tracker, as relayr reads it (lattice RFC-0004): a run shows
 * the items its causal chain filed, or commented on, as "Filed as", with their links.
 */

import type { Filed } from "./queries";

/** An item in a task tracker, as a run shows it: as a `tracker:` event names it, or as filed. */
export interface TrackerItem {
  /** The tracker, by its integration's name after `tracker:`, such as `plane`. */
  readonly tracker: string;
  /** What people call it there, such as `OPS-12`. */
  readonly name: string;
  /** Its address in the tracker's web app, if relayr could make one. */
  readonly link: string | null;
  /** Whether a person deleted it. */
  readonly deleted?: boolean;
}

/** The items a causal chain filed or commented on, the newest first; none with no tracker. */
export function filedBy(filed: Filed | null | undefined, chain: string): TrackerItem[] {
  if (!filed || chain === "") {
    return [];
  }
  return filed.items
    .filter((item) => item.chains.includes(chain))
    .map(({ name, link, deleted }) => ({ tracker: filed.tracker, name, link, deleted }));
}
