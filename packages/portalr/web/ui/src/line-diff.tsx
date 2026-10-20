import type { Change } from "@portalr/client";
import { Fragment, useState } from "react";
import { Button } from "./button";
import { cn } from "./cn";
import { ScrollRegion } from "./scroll-region";

/** The unchanged lines kept on each side of a change; longer runs of them are folded. */
export const CONTEXT_LINES = 3;

/** A line of a comparison: kept, added or removed, with its number in the version it is in. */
interface Line {
  readonly kind: Change["kind"];
  readonly text: string;
  readonly number: number;
}

/** A run of unchanged lines, folded, or a line shown. */
type Row = { readonly line: Line } | { readonly folded: readonly Line[]; readonly at: number };

/** Changes cut by line as lines, each numbered in the later version, or the earlier if removed. */
function linesOf(changes: readonly Change[]): Line[] {
  const lines: Line[] = [];
  let before = 0;
  let after = 0;
  for (const change of changes) {
    const texts = change.text.split("\n");
    if (texts.at(-1) === "") {
      texts.pop(); // the newline that ends the run's last line
    }
    for (const text of texts) {
      if (change.kind === "removed") {
        before += 1;
        lines.push({ kind: "removed", text, number: before });
      } else {
        after += 1;
        before += change.kind === "same" ? 1 : 0;
        lines.push({ kind: change.kind, text, number: after });
      }
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
function LineRow({ line }: { line: Line }) {
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
        <span className={mark}>{line.text}</span>
      )}
    </>
  );
}

/**
 * What changed between two versions of a source, line by line (portalr ADR-0053): each added line
 * marked `+` on the wash, edged in the working colour, each removed one `−`, edged in red and
 * muted, and each a `<ins>` or a `<del>` that a screen reader says is one; the unchanged lines
 * between changes folded, to be shown on asking. Null changes, too large to compare, say so.
 */
export function LineDiff({ changes, name }: { changes: readonly Change[] | null; name: string }) {
  const [unfolded, setUnfolded] = useState<ReadonlySet<number>>(new Set());
  if (changes === null) {
    return <p className="text-muted text-sm italic">Too large to compare.</p>;
  }
  const rows = rowsOf(linesOf(changes));
  return (
    <ScrollRegion
      aria-label={`Changes to the ${name}`}
      className="max-h-[32rem] overflow-y-auto rounded-md border border-line bg-paper"
    >
      <div
        dir="ltr"
        className="grid grid-cols-[auto_auto_minmax(0,1fr)] py-1 font-mono text-fg text-sm [font-variant-ligatures:none]"
      >
        {rows.map((row) =>
          "line" in row ? (
            <LineRow key={`${row.line.kind}:${row.line.number}`} line={row.line} />
          ) : unfolded.has(row.at) ? (
            <Fragment key={`fold:${row.at}`}>
              {row.folded.map((line) => (
                <LineRow key={`same:${line.number}`} line={line} />
              ))}
            </Fragment>
          ) : (
            <div
              key={`fold:${row.at}`}
              className="col-span-3 border-line border-y bg-surface px-2 py-0.5"
            >
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setUnfolded(new Set([...unfolded, row.at]))}
              >
                Show {row.folded.length} unchanged lines
              </Button>
            </div>
          ),
        )}
      </div>
    </ScrollRegion>
  );
}
