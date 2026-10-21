/**
 * A tenant's log records, newest first, as a virtualized list beside the chosen record's details
 * (portalr ADR-0031). A record is what a read gives of it: its time, level, service, thread, run
 * and its line's length, and the labels known to be safe. Its line isn't in the read: it is asked
 * for, one record's at a time, and the caller gives it back through `reveal`.
 *
 * The list is an ARIA listbox the arrow keys, Home, End and the page keys walk. Its rows are
 * drawn as they come into view, so a thousand records draw a screenful. The chosen row is the
 * list's one tab stop, and the list itself is one while the chosen row isn't drawn.
 */

import type { LogRecord } from "@portalr/client";
import { useVirtualizer } from "@tanstack/react-virtual";
import { type KeyboardEvent, type ReactNode, useId, useRef, useState } from "react";
import { Alert } from "./alert";
import { AnsiText } from "./ansi";
import { Button } from "./button";
import { cn } from "./cn";
import { Reading } from "./skeleton";
import { StatusBadge, type Tone } from "./status-badge";
import type { Standing } from "./trace-view";

/** The height of a row, in pixels: two lines. */
const ROW = 52;

/** How many records the page keys move by. */
const PAGE = 10;

/** What a level is shown as: a shape and a word, never a colour alone. */
const LEVELS: ReadonlyMap<string, Tone> = new Map<string, Tone>([
  ["critical", "failed"],
  ["fatal", "failed"],
  ["error", "failed"],
  ["warn", "near"],
  ["warning", "near"],
  ["info", "done"],
  ["debug", "queued"],
  ["trace", "queued"],
]);

/** What the caller does about a record's line: it reads it, for a record, when one asks. */
export interface LineReveal {
  /** Where one record's line stands. */
  standing(id: string): Standing;
  /** The line, once it has been read. */
  line(id: string): string | null;
  /** A record asked to see its line. */
  ask(id: string): void;
}

/** A record's time of day, to the millisecond, in the reader's zone, as a row shows it. */
const time = (ns: number) => {
  const at = new Date(ns / 1_000_000);
  return `${at.toLocaleTimeString(undefined, { hourCycle: "h23" })}.${String(at.getMilliseconds()).padStart(3, "0")}`;
};

/** A record's day and time, and the reader's zone: `10/15/2026, 09:12:03.512 PDT`. */
const moment = (ns: number) => {
  const at = new Date(ns / 1_000_000);
  const zone = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" })
    .formatToParts(at)
    .find((part) => part.type === "timeZoneName")?.value;
  return `${at.toLocaleDateString()}, ${time(ns)}${zone ? ` ${zone}` : ""}`;
};

/** Log records as a list and a record's details; `complete` says whether these are all. */
export function LogList({
  records,
  complete,
  reveal,
}: {
  records: readonly LogRecord[];
  complete: boolean;
  reveal: LineReveal;
}) {
  const base = useId();
  const [chosen, setChosen] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  /** The row the keyboard chose, to be focused as its row is drawn, however far it scrolled. */
  const pending = useRef<string | null>(null);
  const virtual = useVirtualizer({
    count: records.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW,
    overscan: 8,
  });
  // The chosen record is one of these: the first, if what was chosen isn't, as in other records.
  const at = Math.max(
    0,
    records.findIndex((each) => each.id === chosen),
  );
  const current = records[at] ?? null;
  const items = virtual.getVirtualItems();
  const windowed = items.some((item) => item.index === at);

  function choose(index: number) {
    const clamped = Math.min(Math.max(index, 0), records.length - 1);
    const next = records[clamped];
    if (next) {
      pending.current = next.id;
      setChosen(next.id);
      // One scroll, to where the row's fixed height puts it: `scrollToIndex` retries over the
      // frames that follow, and a retry left from an earlier key scrolls back to its row.
      const [offset] = virtual.getOffsetForIndex(clamped, "auto") ?? [0];
      virtual.scrollToOffset(offset);
    }
  }

  function walk(event: KeyboardEvent<HTMLDivElement>) {
    const keys: Record<string, () => void> = {
      ArrowDown: () => choose(at + 1),
      ArrowUp: () => choose(at - 1),
      PageDown: () => choose(at + PAGE),
      PageUp: () => choose(at - PAGE),
      Home: () => choose(0),
      End: () => choose(records.length - 1),
    };
    const act = keys[event.key];
    if (act) {
      event.preventDefault();
      act();
    }
  }

  if (records.length === 0) {
    return <p className="text-muted text-sm">No log records in this window.</p>;
  }
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <section aria-labelledby={`${base}-records`} className="flex min-w-0 flex-col gap-2">
        <h3 id={`${base}-records`} className="font-semibold text-fg text-sm">
          {records.length} {records.length === 1 ? "record" : "records"}, newest first
        </h3>
        {!complete && (
          <Alert tone="warn">
            These are the newest: there may be more. A shorter window, or a thread or a run, finds
            the rest.
          </Alert>
        )}
        <div
          ref={scroller}
          role="listbox"
          aria-labelledby={`${base}-records`}
          // The list is a tab stop of its own while the record chosen isn't drawn, so the keyboard
          // can always get in: it then draws the record, and moves focus to it.
          tabIndex={windowed ? -1 : 0}
          onFocus={(event) => {
            if (
              event.target === event.currentTarget &&
              event.currentTarget.matches(":focus-visible")
            ) {
              choose(at);
            }
          }}
          onKeyDown={walk}
          className="max-h-[30rem] min-h-24 overflow-auto rounded-(--card-radius) border border-line bg-surface"
        >
          <div style={{ height: virtual.getTotalSize() }} className="relative w-full">
            {items.map((item) => {
              const record = records[item.index];
              if (!record) {
                return null;
              }
              const on = item.index === at;
              return (
                <div
                  key={record.id}
                  ref={(node) => {
                    if (node && pending.current === record.id) {
                      pending.current = null;
                      node.focus({ preventScroll: true });
                    }
                  }}
                  role="option"
                  aria-selected={on}
                  aria-posinset={item.index + 1}
                  aria-setsize={records.length}
                  aria-label={label(record)}
                  tabIndex={on ? 0 : -1}
                  onFocus={() => setChosen(record.id)}
                  style={{ height: ROW, transform: `translateY(${item.start}px)` }}
                  className={cn(
                    "absolute inset-x-0 top-0 flex cursor-default flex-col justify-center gap-0.5 border-line border-b px-3 text-(length:--table-text) -outline-offset-(--focus-offset) focus-visible:outline-(length:--focus-width) focus-visible:outline-focus",
                    on ? "bg-wash" : "hover:bg-wash/60",
                  )}
                >
                  <div aria-hidden="true" className="flex min-w-0 items-center gap-2">
                    <span className="shrink-0 font-mono text-xs tabular-nums">
                      {time(record.time_ns)}
                    </span>
                    {record.level && (
                      <StatusBadge tone={LEVELS.get(record.level) ?? "stopped"}>
                        {record.level}
                      </StatusBadge>
                    )}
                    <span className="truncate font-semibold">{record.service ?? "–"}</span>
                  </div>
                  <div aria-hidden="true" className="truncate text-muted text-xs">
                    {[record.thread, record.run, `${record.length} characters`]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>
      {current && <Details key={current.id} record={current} reveal={reveal} />}
    </div>
  );
}

/** A record's name for assistive technology: when, how bad, whose, and how long. */
const label = (record: LogRecord) =>
  [
    time(record.time_ns),
    record.level,
    record.service,
    record.thread && `thread ${record.thread}`,
    record.run && `run ${record.run}`,
    `${record.length} characters`,
  ]
    .filter(Boolean)
    .join(", ");

/** The chosen record: what it is, its labels, what was withheld, and its line, asked for. */
function Details({ record, reveal }: { record: LogRecord; reveal: LineReveal }) {
  const base = useId();
  const labels = Object.entries(record.labels).sort(([a], [b]) => a.localeCompare(b));
  return (
    <section
      aria-labelledby={`${base}-record`}
      className="flex min-w-0 flex-col gap-3 rounded-(--card-radius) border border-line bg-surface p-4"
    >
      <h3 id={`${base}-record`} className="font-semibold text-fg">
        {moment(record.time_ns)}
      </h3>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
        {record.level && <Fact term="Level">{record.level}</Fact>}
        {record.service && <Fact term="Service">{record.service}</Fact>}
        {record.thread && <Fact term="Thread">{record.thread}</Fact>}
        {record.run && <Fact term="Run">{record.run}</Fact>}
        <Fact term="Line">{record.length} characters</Fact>
      </dl>
      <section aria-labelledby={`${base}-line`} className="flex flex-col gap-2">
        <h4 id={`${base}-line`} className="font-semibold text-fg text-sm">
          Line
        </h4>
        <LineNow record={record} reveal={reveal} />
      </section>
      {record.withheld.length > 0 && (
        <p className="break-words text-muted text-xs">
          Labels kept out: <span className="font-mono">{record.withheld.join(", ")}</span>
        </p>
      )}
      <section aria-labelledby={`${base}-labels`} className="flex flex-col gap-1">
        <h4 id={`${base}-labels`} className="font-semibold text-fg text-sm">
          Labels
        </h4>
        <dl className="flex flex-col gap-2 text-xs">
          {labels.map(([key, value]) => (
            <div key={key} className="flex min-w-0 flex-col">
              <dt className="break-words font-mono text-muted">{key}</dt>
              <dd className="min-w-0 break-all font-mono text-fg">{value}</dd>
            </div>
          ))}
        </dl>
      </section>
    </section>
  );
}

/** Where a record's line stands, and what to do about it. */
function LineNow({ record, reveal }: { record: LogRecord; reveal: LineReveal }) {
  switch (reveal.standing(record.id)) {
    case "hidden":
      return (
        <>
          <p className="text-muted text-sm">
            A line is kept out of the list: it may hold what a person or a model said. It is read
            for this record alone, when you ask.
          </p>
          <Button variant="secondary" className="self-start" onClick={() => reveal.ask(record.id)}>
            Show this line
          </Button>
        </>
      );
    case "reading":
      return <Reading>Reading…</Reading>;
    case "failed":
      return <Alert tone="error">The line couldn't be read.</Alert>;
    case "read": {
      const line = reveal.line(record.id);
      return line === null ? (
        <p className="text-muted text-sm">The read returned no such record.</p>
      ) : (
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-(--code-block-radius) bg-paper p-(--code-panel-pad) font-mono text-fg text-xs">
          <AnsiText line={line} />
        </pre>
      );
    }
  }
}

/** One fact of a record: its term, and what it is. */
function Fact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted">{term}</dt>
      <dd className="min-w-0 break-words text-fg">{children}</dd>
    </>
  );
}
