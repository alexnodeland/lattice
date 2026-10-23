import type { Change } from "@portalr/client/diff";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "./button";
import { cn } from "./cn";
import { ScrollRegion } from "./scroll-region";

/** The most lines drawn at first, and drawn more at a time on asking: a long change can't hold the page. */
export const MOST_LINES = 400;

/** The unchanged lines kept on each side of a change; longer runs of them are folded. */
export const CONTEXT_LINES = 3;

/**
 * A line of a comparison: kept, added or removed, with its number in the version before, unless
 * it was added, and in this version, unless it was removed.
 */
interface Line {
  readonly kind: Change["kind"];
  readonly text: string;
  readonly was: number | null;
  readonly number: number | null;
}

/** A run of unchanged lines, folded, or a line shown. */
type Row = { readonly line: Line } | { readonly folded: readonly Line[]; readonly at: number };

/** Changes cut by line as lines, each numbered in the versions it is in. */
function linesOf(changes: readonly Change[]): Line[] {
  const lines: Line[] = [];
  let before = 0;
  let after = 0;
  for (const change of changes) {
    const texts = change.text.split(/\r?\n/);
    if (texts.at(-1) === "") {
      texts.pop(); // the newline that ends the run's last line
    }
    for (const text of texts) {
      before += change.kind === "added" ? 0 : 1;
      after += change.kind === "removed" ? 0 : 1;
      lines.push({
        kind: change.kind,
        text,
        was: change.kind === "added" ? null : before,
        number: change.kind === "removed" ? null : after,
      });
    }
  }
  return lines;
}

/** How many lines changes cut by line add and remove. */
export function lineCounts(changes: readonly Change[]): { added: number; removed: number } {
  const lines = linesOf(changes);
  return {
    added: lines.filter((line) => line.kind === "added").length,
    removed: lines.filter((line) => line.kind === "removed").length,
  };
}

/** The lines as rows: each change with `CONTEXT_LINES` kept lines around it, longer runs folded. */
function rowsOf(lines: readonly Line[]): Row[] {
  const near = lines.map((_, at) =>
    lines
      .slice(Math.max(0, at - CONTEXT_LINES), at + CONTEXT_LINES + 1)
      .some((line) => line.kind !== "same"),
  );
  const rows: Row[] = [];
  let run: Line[] = [];
  // A lone unchanged line is shown: a fold of one would hide nothing worth hiding.
  const fold = (at: number) => {
    if (run.length === 1) {
      rows.push({ line: run[0] as Line });
    } else if (run.length > 1) {
      rows.push({ folded: run, at });
    }
    run = [];
  };
  lines.forEach((line, at) => {
    if (near[at]) {
      fold(at);
      rows.push({ line });
    } else {
      run.push(line);
    }
  });
  fold(lines.length);
  return rows;
}

const SIGN = { added: "+", removed: "−", same: " " } as const;

/** One line: its sign, its number and its text, an added or a removed one said so to a reader. */
function LineRow({ line, focused = false }: { line: Line; focused?: boolean }) {
  const text = useRef<HTMLSpanElement>(null);
  // The first line a fold shows takes the focus of the button it replaced, once.
  useEffect(() => {
    if (focused) {
      text.current?.focus();
    }
  }, [focused]);
  const mark = cn(
    "border-s-2 ps-2 pe-3 whitespace-pre-wrap break-words",
    line.kind === "added" && "border-accent bg-wash no-underline",
    line.kind === "removed" && "border-status-failed text-muted no-underline",
    line.kind === "same" && "border-transparent forced-colors:border-system-canvas",
  );
  const gutter = "select-none px-2 text-end text-muted";
  return (
    <>
      <span aria-hidden="true" className={gutter}>
        {line.was}
      </span>
      <span aria-hidden="true" className={gutter}>
        {line.number}
      </span>
      <span
        aria-hidden="true"
        className={cn(gutter, "px-1 text-center", line.kind !== "same" && "font-semibold text-fg")}
      >
        {SIGN[line.kind]}
      </span>
      {line.kind === "added" ? (
        <ins className={mark}>
          <span className="sr-only">added: </span>
          {line.text}
        </ins>
      ) : line.kind === "removed" ? (
        <del className={mark}>
          <span className="sr-only">removed: </span>
          {line.text}
        </del>
      ) : (
        <span
          className={cn(
            mark,
            "focus-visible:outline-(length:--focus-width) focus-visible:outline-focus",
          )}
          ref={text}
          {...(focused && { tabIndex: -1 })}
        >
          {line.text}
        </span>
      )}
    </>
  );
}

/**
 * What changed between two versions of a source, line by line (portalr ADR-0054): each added line
 * marked `+` on the wash, edged in the working colour, each removed one `−`, edged in red and
 * muted, and each a `<ins>` or a `<del>` that a screen reader says is one; the unchanged lines
 * between changes folded, to be shown on asking. Null changes, too large to compare, say so.
 */
export function LineDiff({ changes, name }: { changes: readonly Change[] | null; name: string }) {
  // How many lines of each fold are shown: a long run of them shows MOST_LINES at a time.
  const [unfolded, setUnfolded] = useState<ReadonlyMap<number, number>>(new Map());
  // The fold last opened, whose first line takes the focus its button had.
  const [opened, setOpened] = useState<{ fold: number; first: number } | null>(null);
  const [limit, setLimit] = useState(MOST_LINES);
  const rows = useMemo(() => (changes === null ? null : rowsOf(linesOf(changes))), [changes]);
  if (rows === null) {
    return <p className="text-muted text-sm italic">Too large to compare.</p>;
  }
  // The rows drawn, as many lines as `limit`, a fold counting as one.
  const drawn: ReactNode[] = [];
  let lines = 0;
  for (const row of rows) {
    if (lines >= limit) {
      break;
    }
    if ("line" in row) {
      drawn.push(<LineRow key={`${row.line.was}:${row.line.number}`} line={row.line} />);
      lines += 1;
    } else {
      const shownOf = unfolded.get(row.at) ?? 0;
      row.folded.slice(0, shownOf).forEach((line, at) => {
        drawn.push(
          <LineRow
            key={`${line.was}:${line.number}`}
            line={line}
            focused={at === opened?.first && opened.fold === row.at}
          />,
        );
      });
      lines += shownOf;
      const left = row.folded.length - shownOf;
      if (left > 0) {
        drawn.push(
          <div
            key={`fold:${row.at}`}
            className="col-span-4 border-line border-y bg-surface px-2 py-0.5"
          >
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setUnfolded(new Map([...unfolded, [row.at, shownOf + Math.min(left, MOST_LINES)]]));
                setOpened({ fold: row.at, first: shownOf });
              }}
            >
              {left > MOST_LINES
                ? `Show ${MOST_LINES} of ${left} unchanged lines`
                : `Show ${left} unchanged lines`}
            </Button>
          </div>,
        );
        lines += 1;
      }
    }
  }
  const total = rows.reduce((sum, row) => {
    if ("line" in row) {
      return sum + 1;
    }
    const shownOf = unfolded.get(row.at) ?? 0;
    return sum + shownOf + (shownOf < row.folded.length ? 1 : 0);
  }, 0);
  return (
    <div className="flex flex-col gap-1">
      <ScrollRegion
        aria-label={`Changes to the ${name}`}
        className="max-h-(--code-block-max-height) overflow-y-auto rounded-(--code-block-radius) border border-line bg-paper"
      >
        <div
          dir="ltr"
          className="grid grid-cols-[auto_auto_auto_minmax(0,1fr)] py-1 font-mono text-fg text-sm [font-variant-ligatures:none]"
        >
          {drawn}
        </div>
      </ScrollRegion>
      {total > limit && (
        <Button
          variant="ghost"
          size="sm"
          className="self-start"
          onClick={() => setLimit(limit + MOST_LINES)}
        >
          Show {Math.min(MOST_LINES, total - limit)} more lines of {total - limit}
        </Button>
      )}
    </div>
  );
}
