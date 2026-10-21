/**
 * A tracker, adapted from Tremor's Tracker (Apache-2.0; see NOTICE): a row of blocks, one for
 * each day, say, each in the mark of its level, such as a day's spend against its share of a
 * budget. The levels take the muted line, then the inks, as marks and never as text; the blocks
 * touch, so the last, over its budget, is hatched, and the mode hatches the rest (portalr
 * ADR-0036), so colour is never its only cue. Each level is named in a legend, each block in a
 * title, and the figures are a table beneath, for those who read them rather than look.
 */

import type { CSSProperties } from "react";
import { useId } from "react";
import { ADJACENT, ink, Legend } from "./chart-theme";
import { Disclosure } from "./disclosure";
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

/** A stripe of an ink, then the same ink hatched over by the surface where the mode asks, at an angle. */
const stripes = (colour: string, angle: number) =>
  `repeating-linear-gradient(${angle}deg, ${colour} 0 3px, color-mix(in srgb, ${colour}, var(--surface) calc(var(--chart-hatch) * 100%)) 3px 6px)`;

/** The levels' marks, the least first: nothing, then each ink, the last, over budget, hatched whatever the mode. */
const MARKS: readonly CSSProperties[] = [
  { background: "var(--line)" },
  { background: ink(0) },
  { background: stripes(ink(1), 135) },
  { ...ADJACENT, background: stripes(ink(2), 45) },
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
      <Legend
        entries={levels.slice(0, MARKS.length).map((level, at) => ({
          key: level.key,
          name: level.name,
          mark: (
            <span aria-hidden="true" className="h-2.5 w-4 shrink-0 rounded-xs" style={mark(at)} />
          ),
        }))}
      />
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
      <Disclosure summary="Show the figures" className="text-sm">
        <ItemTable
          caption={label}
          columns={columns}
          items={blocks}
          keyOf={(block) => block.key}
          empty={{ title: "No figures", body: "Nothing in this tracker yet." }}
        />
      </Disclosure>
    </figure>
  );
}
