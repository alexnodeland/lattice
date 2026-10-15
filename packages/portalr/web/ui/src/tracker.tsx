/**
 * A tracker, adapted from Tremor's Tracker (Apache-2.0; see NOTICE): a row of blocks, one for
 * each day, say, each in the mark of its level, such as a day's spend against its share of a
 * budget. The chart rule (portalr ADR-0021) holds: the levels take the muted line, then the
 * inks, as marks and never as text, and each past the second has a pattern too, so colour is
 * never its only cue: none, solid, striped, then hatched. Each level is named in a legend, each
 * block in a title, and the figures are a table beneath, for those who read them rather than look.
 */

import type { CSSProperties } from "react";
import { useId } from "react";
import { type Column, ItemTable } from "./item-table";

/** One of a tracker's levels: its key, and its name, as the legend and the table give it. */
export interface Level {
  readonly key: string;
  readonly name: string;
}

/** One block of a tracker: its key, its name, such as its day, its level's place, and its figure. */
export interface Block {
  readonly key: string;
  readonly name: string;
  readonly level: number;
  readonly figure: string;
}

/** A stripe of an ink, then a wash of it, at an angle: a level's pattern past solid. */
const stripes = (ink: string, angle: number) =>
  `repeating-linear-gradient(${angle}deg, ${ink} 0 3px, color-mix(in srgb, ${ink} 35%, transparent) 3px 6px)`;

const MARKS: readonly CSSProperties[] = [
  { background: "var(--line)" },
  { background: "var(--chart-1)" },
  { background: stripes("var(--chart-3)", 0) },
  { background: stripes("var(--chart-2)", 45) },
];

/** A level's mark, by its place: past the last, the muted line's. A tracker names `MARKS.length`. */
const mark = (level: number): CSSProperties => MARKS[level] ?? { background: "var(--line)" };

/** A tracker: its blocks in a row, its levels named in a legend, and its figures as a table. */
export function Tracker({
  label,
  levels,
  blocks,
  index,
  figure,
}: {
  label: string;
  /** The levels, the least first: as many as the tracker has marks for, four. */
  levels: readonly Level[];
  blocks: readonly Block[];
  /** What the blocks are, as the table's first column names them, such as "Day (UTC)". */
  index: string;
  /** What each block's figure is, as the table names it, such as "Spend". */
  figure: string;
}) {
  const caption = useId();
  const columns: [Column<Block>, ...Column<Block>[]] = [
    { key: "name", label: index, cell: (block) => block.name },
    { key: "figure", label: figure, cell: (block) => block.figure },
    { key: "level", label: "Level", cell: (block) => levels[block.level]?.name ?? "–" },
  ];
  return (
    <figure aria-labelledby={caption} className="flex flex-col gap-2">
      <figcaption id={caption} className="font-semibold text-fg text-sm">
        {label}
      </figcaption>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-muted text-xs">
        {levels.slice(0, MARKS.length).map((level, at) => (
          <li key={level.key} className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="h-2.5 w-4 shrink-0 rounded-xs" style={mark(at)} />
            {level.name}
          </li>
        ))}
      </ul>
      <div aria-hidden="true" className="flex h-8 w-full items-stretch">
        {blocks.map((block) => (
          <div
            key={block.key}
            title={[`${block.name}: ${block.figure}`, levels[block.level]?.name]
              .filter(Boolean)
              .join(", ")}
            data-level={block.level}
            className="flex-1 px-px first:rounded-l-sm first:pl-0 last:rounded-r-sm last:pr-0"
          >
            <div className="size-full rounded-[1px]" style={mark(block.level)} />
          </div>
        ))}
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted">Show the figures</summary>
        <ItemTable
          caption={label}
          columns={columns}
          items={blocks}
          keyOf={(block) => block.key}
          empty={{ title: "No figures", body: "Nothing in this tracker yet." }}
        />
      </details>
    </figure>
  );
}
