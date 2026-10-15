/**
 * A trace: its spans as a tree beside a waterfall, and, for the one chosen, its details (portalr
 * ADR-0030). It is written for `ui`, from the shape of AgentPrism's views but not its code.
 *
 * The tree is an ARIA tree, which the arrow keys walk and fold, and its rows are virtualized,
 * so a trace of thousands of spans draws only those in view. What was said in a span, its prompt
 * and completion, is not here until a person asks for that span's: the caller reads it then, and
 * gives the view the trace with it.
 */

import type { Kind, Outline, Row } from "@portalr/client";
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
import { type KeyboardEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "./button";
import { cn } from "./cn";
import { Icon } from "./icon";
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

/** Where what was said in a span stands: not asked for, being read, read, or not readable. */
export type Standing = "hidden" | "reading" | "read" | "failed";

/** A row with its place among its siblings, as the tree's ARIA wants it. */
interface Placed {
  readonly row: Row;
  readonly index: number;
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
    return { row, index: 0, among, of: counts.get(parent) ?? 1 };
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
    shown.push({ ...each, index: shown.length });
  }
  return shown;
}

/** A trace's spans as a tree and a waterfall, with the chosen span's details beside or below. */
export function TraceView({
  outline,
  said: standing,
  onAskToSee,
}: {
  outline: Outline;
  /** Where the trace's content stands: the caller reads it when a span asks. */
  said: Standing;
  /** A span asked to see what was said in it: the caller reads it, and gives the trace with it. */
  onAskToSee: () => void;
}) {
  const all = useMemo(() => placed(outline.rows), [outline.rows]);
  const [folded, setFolded] = useState<ReadonlySet<string>>(new Set());
  const [chosen, setChosen] = useState<string | null>(outline.rows[0]?.id ?? null);
  const [asked, setAsked] = useState<ReadonlySet<string>>(new Set());
  const shown = useMemo(() => visible(all, folded), [all, folded]);
  const scroller = useRef<HTMLDivElement>(null);
  const focusing = useRef(false);
  const virtual = useVirtualizer({
    count: shown.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW,
    overscan: 8,
  });
  const at = Math.max(
    0,
    shown.findIndex((each) => each.row.id === chosen),
  );
  const current = shown[at]?.row ?? null;

  // Focus follows the choice made with the keyboard, once its row is drawn.
  useEffect(() => {
    if (focusing.current && chosen) {
      scroller.current?.querySelector<HTMLElement>(`[data-span="${CSS.escape(chosen)}"]`)?.focus();
    }
  });

  function choose(index: number) {
    const next = shown[Math.min(Math.max(index, 0), shown.length - 1)];
    if (next) {
      focusing.current = true;
      setChosen(next.row.id);
      virtual.scrollToIndex(next.index);
    }
  }

  function fold(id: string, on: boolean) {
    setFolded((before) => {
      const after = new Set(before);
      if (on) {
        after.add(id);
      } else {
        after.delete(id);
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
          fold(current.id, false);
        } else if (current.parent) {
          choose(at + 1);
        }
      },
      ArrowLeft: () => {
        if (current.parent && !folded.has(current.id)) {
          fold(current.id, true);
        } else if (current.depth > 0) {
          // To its parent: the nearest row above that is shallower.
          const above = shown.slice(0, at).findLast((each) => each.row.depth < current.depth);
          if (above) {
            choose(above.index);
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
      <section aria-labelledby="spans" className="flex min-w-0 flex-col gap-2">
        <div className="flex items-baseline justify-between gap-3">
          <h2 id="spans" className="font-semibold text-fg text-sm">
            Spans
          </h2>
          <span className="text-muted text-xs">
            {outline.rows.length} {outline.rows.length === 1 ? "span" : "spans"} in{" "}
            {duration(outline.duration)}
          </span>
        </div>
        <div
          ref={scroller}
          role="tree"
          aria-labelledby="spans"
          tabIndex={-1}
          onKeyDown={walk}
          onBlur={() => {
            focusing.current = false;
          }}
          className="max-h-[28rem] min-h-24 overflow-auto rounded-lg border border-line bg-surface"
        >
          <div style={{ height: virtual.getTotalSize() }} className="relative w-full min-w-[26rem]">
            {virtual.getVirtualItems().map((item) => {
              const each = shown[item.index];
              if (!each) {
                return null;
              }
              const { row } = each;
              const open = row.parent ? !folded.has(row.id) : undefined;
              const on = row.id === chosen;
              return (
                <div
                  key={row.id}
                  role="treeitem"
                  data-span={row.id}
                  aria-level={row.depth + 1}
                  aria-setsize={each.of}
                  aria-posinset={each.among}
                  aria-selected={on}
                  {...(open !== undefined && { "aria-expanded": open })}
                  aria-label={`${row.name}, ${KINDS[row.kind].word}, ${duration(row.duration)}${row.error ? ", failed" : ""}`}
                  tabIndex={on ? 0 : -1}
                  onFocus={() => {
                    focusing.current = true;
                    setChosen(row.id);
                  }}
                  style={{ height: ROW, transform: `translateY(${item.start}px)` }}
                  className={cn(
                    "absolute inset-x-0 top-0 grid cursor-default grid-cols-[minmax(11rem,2fr)_minmax(8rem,3fr)_4.5rem] items-center gap-3 border-line border-b px-2 text-sm outline-offset-[-2px] focus-visible:outline-2 focus-visible:outline-focus",
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
                          fold(row.id, open === true);
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
                  <span aria-hidden="true" className="text-right text-muted text-xs tabular-nums">
                    {duration(row.duration)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </section>
      {current && (
        <Details
          row={current}
          standing={standing}
          seen={asked.has(current.id)}
          onAskToSee={() => {
            setAsked((before) => new Set(before).add(current.id));
            onAskToSee();
          }}
        />
      )}
    </div>
  );
}

/** A span's bar on the trace's timeline: from when it began, as long as it took. */
function Bar({ row, total }: { row: Row; total: number }) {
  const left = total > 0 ? (row.offset / total) * 100 : 0;
  const width = total > 0 ? Math.max((row.duration / total) * 100, 0.6) : 100;
  return (
    <div aria-hidden="true" className="relative h-4 min-w-0">
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

/** The chosen span: what it is, when, how long, its model, tool and tokens, its attributes, and what was said. */
function Details({
  row,
  standing,
  seen,
  onAskToSee,
}: {
  row: Row;
  standing: Standing;
  seen: boolean;
  onAskToSee: () => void;
}) {
  const attributes = Object.entries(row.attributes).sort(([a], [b]) => a.localeCompare(b));
  const spoken = row.said;
  return (
    <section
      aria-labelledby="span"
      className="flex min-w-0 flex-col gap-3 rounded-lg border border-line bg-surface p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="span" className="min-w-0 break-words font-semibold text-fg">
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
      {(row.withheld.length > 0 || spoken.length > 0) && (
        <section aria-labelledby="said" className="flex flex-col gap-2">
          <h3 id="said" className="font-semibold text-fg text-sm">
            What was said
          </h3>
          {seen && spoken.length > 0 ? (
            spoken.map((part) => (
              <div key={part.label} className="flex flex-col gap-1">
                <span className="text-muted text-xs">{part.label}</span>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-paper p-3 font-mono text-fg text-xs">
                  {part.text}
                </pre>
              </div>
            ))
          ) : seen && standing === "reading" ? (
            <p role="status" className="text-muted text-sm">
              Reading…
            </p>
          ) : seen && standing === "failed" ? (
            <p role="alert" className="text-sm">
              What was said couldn't be read.
            </p>
          ) : seen ? (
            <p className="text-muted text-sm">Nothing was recorded for this span.</p>
          ) : (
            <>
              <p className="text-muted text-sm">
                Prompts and completions are kept out of the trace until you ask for them.
              </p>
              <Button variant="secondary" className="self-start" onClick={onAskToSee}>
                Show what was said
              </Button>
            </>
          )}
        </section>
      )}
      <section aria-labelledby="attributes" className="flex flex-col gap-1">
        <h3 id="attributes" className="font-semibold text-fg text-sm">
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

/** One fact of a span: its term, and what it is. */
function Fact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted">{term}</dt>
      <dd className="min-w-0 break-words text-fg">{children}</dd>
    </>
  );
}
