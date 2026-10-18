/**
 * Native files: a Word document and its kin, kept as a manifest over the file's bytes (lattice
 * RFC-0003). The renderer shows what the manifest holds, the name, type, size, pages and outline,
 * and changes are read from the outline; the app adds what it reads from the server, the pages
 * and who has the file, through `PageStrip` and `FileHolder` (portalr ADR-0048).
 */

import { useId } from "react";
import { capped, type Data, type Renderer } from "./artifacts";
import { Button } from "./button";
import { cn } from "./cn";
import { Skeleton } from "./skeleton";
import { StatusBadge } from "./status-badge";

/** What people call a native file's type, by its media type. */
const TYPES: Readonly<Record<string, string>> = {
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word document",
};

const UNITS = ["bytes", "kB", "MB", "GB"] as const;

/** A size in bytes as people read it, in powers of a thousand: "48 kB", "1.2 MB". */
export function fileSize(bytes: number): string {
  let size = bytes;
  let unit = 0;
  const shown = () => (unit === 0 || size >= 10 ? Math.round(size) : Math.round(size * 10) / 10);
  // Moved up a unit while its figure, as it is shown, would reach a thousand: 999,950 bytes is
  // "1 MB", not "1000 kB".
  while (shown() >= 1000 && unit < UNITS.length - 1) {
    size /= 1000;
    unit += 1;
  }
  return `${shown()} ${UNITS[unit]}`;
}

/** What a manifest says of its file, read without trusting its shape. */
export interface FileFacts {
  readonly name: string;
  readonly type: string;
  readonly size: number | null;
  readonly pages: number | null;
  readonly outline: string;
}

const text = (value: unknown) => (typeof value === "string" ? value : "");
const count = (value: unknown) =>
  typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;

/** A native file's facts, from its manifest: what's missing or malformed is left out. */
export function factsOf(data: Data): FileFacts {
  const content =
    typeof data.content === "object" && data.content !== null
      ? (data.content as Readonly<Record<string, unknown>>)
      : {};
  const mediaType = text(content.media_type);
  return {
    name: text(data.name),
    type: TYPES[mediaType] ?? (mediaType || "File"),
    size: count(content.size),
    pages: count(data.pages),
    outline: text(data.outline),
  };
}

/** A native file's name, type, size, pages and outline. */
function Summary({ facts }: { facts: FileFacts }) {
  const outline = useId();
  // An outline's lines can repeat, so each is keyed by its text and how often it came before.
  const seen = new Map<string, number>();
  const lines = facts.outline
    .split("\n")
    .filter((line) => line.trim() !== "")
    .map((line) => {
      const before = seen.get(line) ?? 0;
      seen.set(line, before + 1);
      return { line, key: `${line}#${before}` };
    });
  const about = [
    facts.type,
    facts.size === null ? null : fileSize(facts.size),
    facts.pages === null ? null : `${facts.pages} ${facts.pages === 1 ? "page" : "pages"}`,
  ].filter(Boolean);
  return (
    <div className="flex flex-col gap-3">
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="break-all font-mono font-semibold text-fg text-sm">
          {facts.name || "Unnamed file"}
        </span>
        <span className="text-muted text-sm">{about.join(" · ")}</span>
      </p>
      {lines.length > 0 ? (
        // Not a heading: a renderer doesn't know how deep in its page it is drawn.
        <section aria-labelledby={outline} className="flex flex-col gap-1">
          <span id={outline} className="font-semibold text-muted text-xs uppercase tracking-wide">
            Outline
          </span>
          <ol className="flex flex-col gap-0.5 border-line border-l-2 pl-3 text-fg text-sm">
            {lines.map(({ line, key }) => (
              <li key={key}>{line}</li>
            ))}
          </ol>
        </section>
      ) : (
        <p className="text-muted text-sm italic">The app read no outline from this file.</p>
      )}
    </div>
  );
}

/**
 * The renderer for a native file's kind, such as `word_document`: its manifest shown, its title
 * its file's name, and its changes read from its outline, line by line, as the RFC has it; the
 * file's own words are compared by the app, from the text the server keeps.
 */
export function nativeFile(): Renderer {
  return {
    render: (data) => <Summary facts={factsOf(data)} />,
    text: (data) => factsOf(data).outline,
    title: (data) => capped(factsOf(data).name),
    diff: "lines",
  };
}

/**
 * Who has a native file: no one; the reader, by a check-out of theirs; someone else, by theirs;
 * or the agent, for the seconds an edit takes. A check-out says until when.
 */
export type Holder =
  | { readonly kind: "free" }
  | { readonly kind: "you"; readonly until: string }
  | { readonly kind: "person"; readonly who: string; readonly until: string }
  | { readonly kind: "agent" };

/** A moment as a time of day, or a date and time when it isn't today. */
function when(at: string, now: Date): string {
  const moment = new Date(at);
  const today = moment.toDateString() === now.toDateString();
  return today
    ? moment.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
    : moment.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/**
 * Who has a native file, as a shape and words, announced as it changes: available, a filled
 * circle; checked out by you, the diamond of what waits for you; by someone else, a dotted ring;
 * an agent editing, the spinner of what is working.
 */
export function FileHolder({ holder, now = new Date() }: { holder: Holder; now?: Date }) {
  switch (holder.kind) {
    case "free":
      return (
        <StatusBadge tone="done" live>
          Available to check out
        </StatusBadge>
      );
    case "you":
      return (
        <StatusBadge tone="waiting" live>
          <span>
            Checked out by you until <time dateTime={holder.until}>{when(holder.until, now)}</time>
          </span>
        </StatusBadge>
      );
    case "person":
      return (
        <StatusBadge tone="queued" live>
          <span>
            Checked out by {holder.who} until{" "}
            <time dateTime={holder.until}>{when(holder.until, now)}</time>
          </span>
        </StatusBadge>
      );
    case "agent":
      return (
        <StatusBadge tone="working" live>
          The agent is editing it
        </StatusBadge>
      );
    default:
      return holder satisfies never;
  }
}

/** One page as the strip shows it: its image, while it is read, or that it couldn't be. */
export type PageShown =
  | { readonly page: number; readonly src: string }
  | { readonly page: number; readonly state: "reading" | "failed" };

/**
 * A file's pages, rendered by its app, each in a box of a page's proportions with its number
 * beneath, side by side as the width allows. Only the pages given are shown; with `onMore`, a
 * button shows more of the `total`. Each image is named by its page, as its caption says.
 */
export function PageStrip({
  label,
  pages,
  total,
  onMore,
  className,
}: {
  /** What the pages are of, such as "Pages of version 3". */
  label: string;
  pages: readonly PageShown[];
  total: number;
  onMore?: (() => void) | undefined;
  className?: string;
}) {
  return (
    <section aria-label={label} className={cn("flex flex-col gap-3", className)}>
      <ol className="grid grid-cols-[repeat(auto-fill,minmax(8.5rem,1fr))] gap-3">
        {pages.map((shown) => {
          const name = `Page ${shown.page} of ${total}`;
          return (
            <li key={shown.page}>
              <figure className="flex flex-col gap-1">
                <div className="flex aspect-[1/1.414] items-center justify-center overflow-hidden rounded-sm border border-line bg-surface forced-colors:border-system-text">
                  {"src" in shown ? (
                    <img src={shown.src} alt={name} className="size-full object-contain" />
                  ) : shown.state === "reading" ? (
                    <Skeleton className="size-full rounded-none" />
                  ) : (
                    <p className="p-2 text-center text-muted text-xs">
                      This page couldn't be shown.
                    </p>
                  )}
                </div>
                {/* An image is named by its page, which its caption says again for the eye. */}
                <figcaption
                  aria-hidden={"src" in shown ? true : undefined}
                  className="text-center text-muted text-xs"
                >
                  {name}
                  {"state" in shown && shown.state === "reading" && (
                    <span className="sr-only">, being read</span>
                  )}
                </figcaption>
              </figure>
            </li>
          );
        })}
      </ol>
      {onMore && pages.length < total && (
        <Button variant="secondary" size="sm" className="self-start" onClick={onMore}>
          Show more pages
        </Button>
      )}
    </section>
  );
}
