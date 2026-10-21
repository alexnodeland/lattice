/**
 * Items in a task tracker, after the words that say how a run is tied to them, such as "Filed as"
 * (lattice RFC-0004): each a link that opens the item in its tracker, in a new tab, which needs no
 * record, since the tracker checks its own access. An item a person deleted, or whose address
 * isn't a web page's, is its name alone, and a deleted one says so in words, not only by a line
 * through it.
 */

import { ExternalLink } from "lucide-react";
import { Icon } from "./icon";
import { safeHref } from "./safe-href";

/** An item in a task tracker: what people call it, which tracker it is in, and its address. */
export interface TrackerItem {
  /** The tracker, by its integration's name after `tracker:`, such as `plane`. */
  readonly tracker: string;
  /** What people call it there, such as `OPS-12`. */
  readonly name: string;
  /** Its address in the tracker's web app, if there is one. */
  readonly link: string | null;
  /** Whether a person deleted it. */
  readonly deleted?: boolean;
}

/** The trackers lattice files into, as people name them; another by its own name. */
const TRACKERS: Readonly<Record<string, string>> = { plane: "Plane", vikunja: "Vikunja" };

/** A tracker as people name it, from its integration's name. */
export const trackerName = (tracker: string) => TRACKERS[tracker] ?? tracker;

/**
 * Items in a task tracker after a label, on one line that wraps; nothing with none. Each opens
 * where its tracker shows it, named aloud with its tracker and that it opens a new tab.
 */
export function TrackerItems({ label, items }: { label: string; items: readonly TrackerItem[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <span className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs">
      <span className="text-muted">{label}</span>
      {items.map((item) => (
        <Item key={`${item.tracker}/${item.name}`} item={item} />
      ))}
    </span>
  );
}

function Item({ item }: { item: TrackerItem }) {
  const where = trackerName(item.tracker);
  const href = item.deleted ? null : safeHref(item.link);
  if (href === null) {
    return (
      <span className="font-mono">
        <span className={item.deleted ? "line-through" : undefined}>{item.name}</span>
        <span className="text-muted">{item.deleted ? ", deleted" : ""}</span>
        <span className="sr-only">, in {where}</span>
      </span>
    );
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      // Its name first, as it is shown, then where it goes.
      aria-label={`${item.name}, in ${where}, opens in a new tab`}
      className="inline-flex items-center gap-1 font-mono text-accent underline underline-offset-2 outline-offset-(--focus-offset) focus-visible:outline-(length:--focus-width) focus-visible:outline-focus"
    >
      {item.name}
      <Icon icon={ExternalLink} className="size-3" />
    </a>
  );
}
