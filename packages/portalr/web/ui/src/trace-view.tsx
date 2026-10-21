/**
 * A trace: its spans as a tree beside a waterfall, and, for the one chosen, its details (portalr
 * ADR-0030). It is written for `ui`, from the shape of AgentPrism's views but not its code.
 *
 * The tree is an ARIA tree, which the arrow keys walk and fold, and its rows are virtualized, so a
 * trace of thousands of spans draws only those in view. A span's attributes that aren't known to
 * be safe, a prompt and a completion among them, aren't in the trace it is given: they are read
 * for one span when a person asks for that span's, and the caller gives them back through `reveal`.
 */

import type { Kind, Outline, Row, Said } from "@portalr/client";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  Bot,
  ChevronDown,
  ChevronRight,
  Circle,
  Database,
  Globe,
  type LucideIcon,
  Sparkles,
  Workflow,
  Wrench,
} from "lucide-react";
import { type KeyboardEvent, type ReactNode, useId, useMemo, useRef, useState } from "react";
import { Alert } from "./alert";
import { Button } from "./button";
import { cn } from "./cn";
import { Icon } from "./icon";
import { Num } from "./num";
import { Reading } from "./skeleton";
import { StatusBadge } from "./status-badge";

/** What each kind of span is called, and the mark beside it. */
const KINDS: Record<Kind, { word: string; mark: LucideIcon }> = {
  workflow: { word: "Workflow", mark: Workflow },
  agent: { word: "Agent", mark: Bot },
  llm: { word: "Model call", mark: Sparkles },
  tool: { word: "Tool", mark: Wrench },
  http: { word: "HTTP request", mark: Globe },
  database: { word: "Database", mark: Database },
  other: { word: "Span", mark: Circle },
};

/** The height of a row of the tree, in pixels. */
const ROW = 36;

/** A duration as people read it: under a millisecond, milliseconds, or seconds. */
export function duration(ms: number): string {
  if (ms < 1) {
    return "<1 ms";
  }
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`;
}

/** Where what a span withheld stands: not asked for, being read, read, or not readable. */
export type Standing = "hidden" | "reading" | "read" | "failed";

/** What the caller does about what spans withhold: it reads it, for a span, when one asks. */
export interface Reveal {
  /** Where one span's withheld attributes stand. */
  standing(id: string): Standing;
  /** What the span withheld, read, each labelled; none if the read had none of its names. */
  parts(row: Row): readonly Said[];
  /** A span asked to see what it withheld. */
  ask(id: string): void;
}

/** A row with its place among its siblings, as the tree's ARIA wants it. */
interface Placed {
  readonly row: Row;
  readonly among: number;
  readonly of: number;
}

/** Each row's place among the siblings that share its parent. */
function placed(rows: readonly Row[]): Placed[] {
  const counts = new Map<string | null, number>();
  const parents = new Map<string, string | null>();
  for (const row of rows) {
    // A row whose parent isn't in the trace is a root: its depth says so.
    const parent = row.depth === 0 ? null : row.parentId;
    parents.set(row.id, parent);
    counts.set(parent, (counts.get(parent) ?? 0) + 1);
  }
  const seen = new Map<string | null, number>();
  return rows.map((row) => {
    const parent = parents.get(row.id) ?? null;
    const among = (seen.get(parent) ?? 0) + 1;
    seen.set(parent, among);
    return { row, among, of: counts.get(parent) ?? 1 };
  });
}

/** The rows in view: those with no folded ancestor. */
function visible(all: readonly Placed[], folded: ReadonlySet<string>): Placed[] {
  const shown: Placed[] = [];
  let hiding: number | null = null;
  for (const each of all) {
    if (hiding !== null && each.row.depth > hiding) {
      continue;
    }
    hiding = folded.has(each.row.id) ? each.row.depth : null;
    shown.push(each);
  }
  return shown;
}

/** A trace's spans as a tree and a waterfall, with the chosen span's details beside or below. */
export function TraceView({ outline, reveal }: { outline: Outline; reveal: Reveal }) {
  const base = useId();
  const all = useMemo(() => placed(outline.rows), [outline.rows]);
  const [folded, setFolded] = useState<ReadonlySet<string>>(new Set());
  const [chosen, setChosen] = useState<string | null>(null);
  const shown = useMemo(() => visible(all, folded), [all, folded]);
  const scroller = useRef<HTMLDivElement>(null);
  /** The row the keyboard chose, to be focused as its row is drawn, however far it scrolled. */
  const pending = useRef<string | null>(null);
  const virtual = useVirtualizer({
    count: shown.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW,
    overscan: 8,
  });
  // What is chosen is a row that is shown: the first, if what was chosen is no longer, as it
  // isn't after its ancestor folds, or in a trace that has changed.
  const at = Math.max(
    0,
    shown.findIndex((each) => each.row.id === chosen),
  );
  const current = shown[at]?.row ?? null;
  const items = virtual.getVirtualItems();
  const windowed = items.some((item) => item.index === at);

  function choose(index: number) {
    const next = shown[Math.min(Math.max(index, 0), shown.length - 1)];
    if (next) {
      pending.current = next.row.id;
      setChosen(next.row.id);
      virtual.scrollToIndex(shown.indexOf(next), { align: "auto" });
    }
  }

  function fold(row: Row, on: boolean) {
    if (on) {
      // What is chosen under what folds goes to what folds, so the choice isn't lost with its row.
      const from = all.findIndex((each) => each.row.id === row.id);
      const under = all.slice(from + 1).findIndex((each) => each.row.depth <= row.depth);
      const inside = all.slice(from + 1, under === -1 ? undefined : from + 1 + under);
      if (inside.some((each) => each.row.id === current?.id)) {
        pending.current = row.id;
        setChosen(row.id);
      }
    }
    setFolded((before) => {
      const after = new Set(before);
      if (on) {
        after.add(row.id);
      } else {
        after.delete(row.id);
      }
      return after;
    });
  }

  function walk(event: KeyboardEvent<HTMLDivElement>) {
    if (!current) {
      return;
    }
    const keys: Record<string, () => void> = {
      ArrowDown: () => choose(at + 1),
      ArrowUp: () => choose(at - 1),
      Home: () => choose(0),
      End: () => choose(shown.length - 1),
      ArrowRight: () => {
        if (current.parent && folded.has(current.id)) {
          fold(current, false);
        } else if (current.parent) {
          choose(at + 1);
        }
      },
      ArrowLeft: () => {
        if (current.parent && !folded.has(current.id)) {
          fold(current, true);
        } else if (current.depth > 0) {
          // To its parent: the nearest row above that is shallower.
          const above = shown.slice(0, at).findLastIndex((each) => each.row.depth < current.depth);
          if (above !== -1) {
            choose(above);
          }
        }
      },
    };
    const act = keys[event.key];
    if (act) {
      event.preventDefault();
      act();
    }
  }

  if (outline.rows.length === 0) {
    return <p className="text-muted text-sm">This trace has no spans.</p>;
  }
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <section aria-labelledby={`${base}-spans`} className="flex min-w-0 flex-col gap-2">
        <div className="flex items-baseline justify-between gap-3">
          <h2 id={`${base}-spans`} className="font-semibold text-fg text-sm">
            Spans
          </h2>
          <span className="text-muted text-xs">
            {outline.rows.length} {outline.rows.length === 1 ? "span" : "spans"} in{" "}
            {duration(outline.duration)}
          </span>
        </div>
        {!outline.complete && (
          <Alert tone="warn">This trace has more spans than are shown: these are its first.</Alert>
        )}
        <div
          ref={scroller}
          role="tree"
          aria-labelledby={`${base}-spans`}
          // The tree is a tab stop of its own while the row chosen isn't drawn, so the keyboard
          // can always get in: it then draws the row, and moves focus to it.
          tabIndex={windowed ? -1 : 0}
          onFocus={(event) => {
            // The keyboard comes in by the tree, and goes on to the chosen row; a click on its
            // blank area isn't asked to move focus.
            if (
              event.target === event.currentTarget &&
              event.currentTarget.matches(":focus-visible")
            ) {
              choose(at);
            }
          }}
          onKeyDown={walk}
          className="@container max-h-[28rem] min-h-24 overflow-auto rounded-lg border border-line bg-surface"
        >
          <div style={{ height: virtual.getTotalSize() }} className="relative w-full">
            {items.map((item) => {
              const each = shown[item.index];
              if (!each) {
                return null;
              }
              const { row } = each;
              const open = row.parent ? !folded.has(row.id) : undefined;
              const on = item.index === at;
              return (
                <div
                  key={row.id}
                  ref={(node) => {
                    if (node && pending.current === row.id) {
                      pending.current = null;
                      node.focus({ preventScroll: true });
                    }
                  }}
                  role="treeitem"
                  aria-level={row.depth + 1}
                  aria-setsize={each.of}
                  aria-posinset={each.among}
                  aria-selected={on}
                  {...(open !== undefined && { "aria-expanded": open })}
                  aria-label={`${row.name}, ${KINDS[row.kind].word}, ${duration(row.duration)}${row.error ? ", failed" : ""}`}
                  tabIndex={on ? 0 : -1}
                  onFocus={() => setChosen(row.id)}
                  style={{ height: ROW, transform: `translateY(${item.start}px)` }}
                  className={cn(
                    "absolute inset-x-0 top-0 grid cursor-default grid-cols-[minmax(0,1fr)_4.5rem] items-center gap-3 border-line border-b px-2 text-sm -outline-offset-(--focus-offset) focus-visible:outline-(length:--focus-width) focus-visible:outline-focus @xl:grid-cols-[minmax(11rem,2fr)_minmax(8rem,3fr)_4.5rem]",
                    on ? "bg-wash" : "hover:bg-wash/60",
                  )}
                >
                  <div
                    style={{ paddingLeft: row.depth * 14 }}
                    className="flex min-w-0 items-center gap-1"
                  >
                    {row.parent ? (
                      <button
                        type="button"
                        tabIndex={-1}
                        aria-hidden="true"
                        onClick={(event) => {
                          event.stopPropagation();
                          fold(row, open === true);
                        }}
                        className="grid size-5 shrink-0 place-items-center rounded-sm text-muted hover:text-fg"
                      >
                        <Icon icon={open ? ChevronDown : ChevronRight} />
                      </button>
                    ) : (
                      <span aria-hidden="true" className="size-5 shrink-0" />
                    )}
                    <Icon icon={KINDS[row.kind].mark} className="text-muted" />
                    <span aria-hidden="true" className="truncate">
                      {row.name}
                    </span>
                    {row.error && (
                      <span aria-hidden="true" className="shrink-0 font-semibold text-xs">
                        Failed
                      </span>
                    )}
                  </div>
                  <Bar row={row} total={outline.duration} />
                  <span aria-hidden="true" className="text-right text-muted text-xs">
                    <Num>{duration(row.duration)}</Num>
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </section>
      {current && <Details key={current.id} row={current} reveal={reveal} />}
    </div>
  );
}

/** A span's bar on the trace's timeline: from when it began, as long as it took. Not on a phone. */
function Bar({ row, total }: { row: Row; total: number }) {
  const left = total > 0 ? (row.offset / total) * 100 : 0;
  const width = total > 0 ? Math.max((row.duration / total) * 100, 0.6) : 100;
  return (
    <div aria-hidden="true" className="relative hidden h-4 min-w-0 @xl:block">
      <div
        style={{ left: `${Math.min(left, 99.4)}%`, width: `${Math.min(width, 100 - left)}%` }}
        className={cn(
          "absolute top-0.5 h-3 min-w-0.5 rounded-sm",
          // A failed span is hatched as well as dark, so it isn't told by its tone alone.
          row.error
            ? "bg-[repeating-linear-gradient(45deg,var(--fg)_0_3px,var(--surface)_3px_6px)] ring-1 ring-fg"
            : "bg-[var(--chart-1)]",
        )}
      />
    </div>
  );
}

/** The chosen span: what it is, when, how long, its model, tool and tokens, its attributes, and what it withheld. */
function Details({ row, reveal }: { row: Row; reveal: Reveal }) {
  const base = useId();
  const attributes = Object.entries(row.attributes).sort(([a], [b]) => a.localeCompare(b));
  return (
    <section
      aria-labelledby={`${base}-span`}
      className="flex min-w-0 flex-col gap-3 rounded-lg border border-line bg-surface p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={`${base}-span`} className="min-w-0 break-words font-semibold text-fg">
          {row.name}
        </h2>
        {row.error && <StatusBadge tone="failed">Failed</StatusBadge>}
      </div>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
        <Fact term="Kind">{KINDS[row.kind].word}</Fact>
        <Fact term="Began">{duration(row.offset)} into the trace</Fact>
        <Fact term="Took">{duration(row.duration)}</Fact>
        {row.model && <Fact term="Model">{row.model}</Fact>}
        {row.tool && <Fact term="Tool">{row.tool}</Fact>}
        {row.tokens && (
          <Fact term="Tokens">
            {row.tokens.input ?? "–"} in, {row.tokens.output ?? "–"} out
          </Fact>
        )}
      </dl>
      {row.withheld.length > 0 && <Withheld row={row} reveal={reveal} />}
      <section aria-labelledby={`${base}-attributes`} className="flex flex-col gap-1">
        <h3 id={`${base}-attributes`} className="font-semibold text-fg text-sm">
          Attributes
        </h3>
        {attributes.length === 0 ? (
          <p className="text-muted text-sm">None.</p>
        ) : (
          <dl className="flex flex-col gap-2 text-xs">
            {attributes.map(([key, value]) => (
              <div key={key} className="flex min-w-0 flex-col">
                <dt className="break-words font-mono text-muted">{key}</dt>
                <dd className="min-w-0 break-all font-mono text-fg">{String(value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>
    </section>
  );
}

/** What a span withheld: its names, and, once asked for, the attributes, which only this span's. */
function Withheld({ row, reveal }: { row: Row; reveal: Reveal }) {
  const heading = useId();
  return (
    <section aria-labelledby={heading} className="flex flex-col gap-2">
      <h3 id={heading} className="font-semibold text-fg text-sm">
        Withheld
      </h3>
      <WithheldNow row={row} reveal={reveal} />
    </section>
  );
}

/** Where a span's withheld attributes stand, and what to do about it. */
function WithheldNow({ row, reveal }: { row: Row; reveal: Reveal }) {
  switch (reveal.standing(row.id)) {
    case "hidden":
      return (
        <>
          <p className="text-muted text-sm">
            {row.withheld.length === 1
              ? "One attribute is"
              : `${row.withheld.length} attributes are`}{" "}
            kept out of the trace, as {row.withheld.length === 1 ? "it isn't" : "they aren't"} known
            to be safe to show: prompts and completions may be among them. They are read for this
            span alone, when you ask.
          </p>
          <p className="break-words font-mono text-muted text-xs">{row.withheld.join(", ")}</p>
          <Button variant="secondary" className="self-start" onClick={() => reveal.ask(row.id)}>
            Show what this span withheld
          </Button>
        </>
      );
    case "reading":
      return <Reading>Reading…</Reading>;
    case "failed":
      return <Alert tone="error">What this span withheld couldn't be read.</Alert>;
    case "read": {
      const parts = reveal.parts(row);
      return parts.length === 0 ? (
        <p className="text-muted text-sm">The read returned none of these attributes.</p>
      ) : (
        parts.map((part) => (
          <div key={part.label} className="flex flex-col gap-1">
            <span className="break-words text-muted text-xs">{part.label}</span>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-paper p-3 font-mono text-fg text-xs">
              {part.text}
            </pre>
          </div>
        ))
      );
    }
  }
}

/** One fact of a span: its term, and what it is. */
function Fact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted">{term}</dt>
      <dd className="min-w-0 break-words text-fg">{children}</dd>
    </>
  );
}
