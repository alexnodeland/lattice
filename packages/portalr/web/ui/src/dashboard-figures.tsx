import { useEffect, useState } from "react";
/**
 * A dashboard's figures, as text, from its panels alone: each chart's "Show the figures" and a
 * table's rows before, or without, the dashboards add-on. Built from the panel, never from what
 * draws it, so a chart drawn another way can't lose its text equivalent (portalr ADR-0047).
 */

import type { Keyed, Panel, Row, TablePanel, TableRow } from "./artifactr-ui";
import { formatNumber, largestFirst } from "./chart-theme";
import { Disclosure } from "./disclosure";
import { type Column, ItemTable } from "./item-table";
import { isNumber, own } from "./json";

/** A cell as it reads: a number grouped, yes or no in words, nothing a dash. */
export function cellText(cell: TableRow[string] | undefined): string {
  if (typeof cell === "boolean") {
    return cell ? "Yes" : "No";
  }
  return isNumber(cell) ? formatNumber(cell) : (cell ?? "–");
}

/** A row with its place, which keys it: rows needn't differ. */
interface Placed {
  readonly row: TableRow;
  readonly at: number;
}

const placed = (rows: readonly (Row | TableRow)[]) => rows.map((row, at) => ({ row, at }));

/** A column of rows by a key, headed by its name. */
const columnOf = (column: Keyed): Column<Placed> => ({
  key: column.key,
  label: column.name,
  cell: ({ row }) => cellText(own(row, column.key) as TableRow[string] | undefined),
});

/** A table of rows by its columns, the first naming each row, named by `labelledBy` or `caption`. */
function Rows({
  columns: [first, ...rest],
  rows,
  ...naming
}: { columns: readonly [Keyed, ...Keyed[]]; rows: readonly (Row | TableRow)[] } & (
  | { caption: string }
  | { labelledBy: string }
)) {
  return (
    <ItemTable
      {...naming}
      columns={[columnOf(first), ...rest.map(columnOf)]}
      items={placed(rows)}
      keyOf={({ at }) => String(at)}
      empty={{ title: "No figures", body: "Nothing here yet." }}
    />
  );
}

/** A table panel's rows, plain: as they are, named by its heading. */
export function PlainTable({ panel, labelledBy }: { panel: TablePanel; labelledBy: string }) {
  return <Rows labelledBy={labelledBy} columns={panel.columns} rows={panel.rows} />;
}

/** A donut's parts, the largest first, each with its share of the whole, as the donut says it. */
function partsOf(panel: Extract<Panel, { type: "donut" }>) {
  const { sorted, share } = largestFirst(panel.parts);
  return sorted.map((part) => ({ part: part.name, value: part.value, share: share(part.value) }));
}

/** A chart panel's figures, under "Show the figures", open where the chart isn't drawn. */
export function Figures({
  panel,
  open = false,
}: {
  panel: Extract<Panel, { type: "bar" | "line" | "donut" }>;
  open?: boolean;
}) {
  // Opened by the person, or by the page once the chart can't be drawn: `open` may turn true after
  // the first render, when the charts' add-on fails to load.
  const [shown, setShown] = useState(open);
  useEffect(() => {
    if (open) {
      setShown(true);
    }
  }, [open]);
  return (
    <Disclosure summary="Show the figures" className="text-sm" open={shown} onOpenChange={setShown}>
      {panel.type === "donut" ? (
        <Rows
          caption={panel.label}
          columns={[
            { key: "part", name: "Part" },
            { key: "value", name: "Value" },
            { key: "share", name: "Share" },
          ]}
          rows={partsOf(panel)}
        />
      ) : (
        <Rows caption={panel.label} columns={[panel.index, ...panel.series]} rows={panel.rows} />
      )}
    </Disclosure>
  );
}
