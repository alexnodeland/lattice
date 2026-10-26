/**
 * What a dashboard draws beyond its figures, loaded with the first dashboard a page shows while
 * `ui:dashboards` is on (portalr ADR-0047): its charts, the kit's own on Recharts and the chart
 * theme, drawn bare, since the dashboard frames each with its caption and its figures; and a table
 * panel's rows, sorted, filtered and paged by TanStack Table, in the kit's `Table`.
 */

import {
  type Cell,
  type Column,
  columnFilteringFeature,
  createColumnHelper,
  createFilteredRowModel,
  createPaginatedRowModel,
  createSortedRowModel,
  globalFilteringFeature,
  type Row,
  rowPaginationFeature,
  rowSortingFeature,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import type { Keyed, Panel, TablePanel, TableRow } from "../artifactr-ui";
import { Button } from "../button";
import { BarChart, DonutChart, LineChart } from "../chart";
import { formatNumber } from "../chart-theme";
import { cellText } from "../dashboard-figures";
import { EmptyState } from "../empty-state";
import { Icon } from "../icon";
import { isNumber, own } from "../json";
import { Table } from "../table";
import { TextField } from "../text-field";
import { TYPE } from "../type";

/** A bar, line or donut panel, as the kit's chart draws it: its legend and plot alone. */
export function Chart({ panel }: { panel: Extract<Panel, { type: "bar" | "line" | "donut" }> }) {
  if (panel.type === "donut") {
    return <DonutChart label={panel.label} parts={panel.parts} bare />;
  }
  const Drawn = panel.type === "bar" ? BarChart : LineChart;
  return (
    <Drawn label={panel.label} index={panel.index} series={panel.series} data={panel.rows} bare />
  );
}

/** The rows a page shows. */
const PAGE = 50;

/** Two cells in order: numbers by value, and everything else by its words; nothing last. */
function compare(a: unknown, b: unknown): number {
  if (isNumber(a) && isNumber(b)) {
    return a - b;
  }
  return cellText(a as TableRow[string]).localeCompare(cellText(b as TableRow[string]), "en-GB", {
    numeric: true,
  });
}

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  columnFilteringFeature,
  globalFilteringFeature,
  filteredRowModel: createFilteredRowModel(),
  rowPaginationFeature,
  paginatedRowModel: createPaginatedRowModel(),
});

const helper = createColumnHelper<typeof features, TableRow>();

/** A column of the panel: its cells by its key, sorted by value, nothing last. */
const columnOf = (column: Keyed) =>
  // A cell that holds nothing, null or left out, is undefined to TanStack, whose `sortUndefined`
  // puts it last.
  helper.accessor((row) => (own(row, column.key) as TableRow[string] | undefined) ?? undefined, {
    id: column.key,
    header: column.name,
    sortFn: (a, b, id) => compare(a.getValue(id), b.getValue(id)),
    sortUndefined: "last",
    // Ascending first, whatever the column holds: TanStack starts a number column descending.
    sortDescFirst: false,
  });

/** Whether a row's cell in a column holds the filter's words, as the cell reads. */
const holds = (row: Row<typeof features, TableRow>, id: string, words: unknown) =>
  cellText(row.getValue(id))
    .toLocaleLowerCase("en-GB")
    .includes(String(words).toLocaleLowerCase("en-GB"));

/** How a column is sorted, as `aria-sort` says it; nothing where it isn't. */
function sortOf(column: Column<typeof features, TableRow, unknown>) {
  const sorted = column.getIsSorted();
  return sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined;
}

/** How long the count waits for the filter's words to settle before it is said. */
const SETTLE = 300;

/** `value`, once it has stayed the same for `SETTLE`: so a count is said once, not each keystroke. */
function useSettled<T>(value: T): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), SETTLE);
    return () => clearTimeout(timer);
  }, [value]);
  return settled;
}

/**
 * A cell of a row: the first column's is the row's header, whose id names the row, as the kit's
 * tables name theirs.
 */
function CellOf({
  cell,
  header,
}: {
  cell: Cell<typeof features, TableRow, unknown>;
  header?: string;
}) {
  const text = cellText(cell.getValue() as TableRow[string] | undefined);
  return header === undefined ? (
    <td>{text}</td>
  ) : (
    <th id={header} scope="row">
      {text}
    </th>
  );
}

/**
 * A table panel's rows, to sort by one column at a time, filter by any words and page through 50
 * at a time, in the kit's `Table`, named by its panel's heading, as its filter and its pages are
 * named by its label. Each column's heading is a button whose column says how it is sorted
 * (`aria-sort`); which rows are shown is said once it settles.
 */
export function DataTable({ panel, labelledBy }: { panel: TablePanel; labelledBy: string }) {
  const named = useId();
  const [words, setWords] = useState("");
  const columns = useMemo(() => helper.columns(panel.columns.map(columnOf)), [panel.columns]);
  const table = useTable({
    features,
    columns,
    data: panel.rows,
    state: { globalFilter: words },
    onGlobalFilterChange: (next) => setWords(typeof next === "function" ? next(words) : next),
    globalFilterFn: holds,
    getColumnCanGlobalFilter: () => true,
    enableMultiSort: false,
    initialState: { pagination: { pageIndex: 0, pageSize: PAGE } },
  });
  const rows = table.getRowModel().rows;
  const matched = table.getFilteredRowModel().rows.length;
  const { pageIndex } = table.state.pagination;
  const first = pageIndex * PAGE;
  const count = useSettled(
    matched === 0
      ? "No rows hold those words."
      : `Rows ${formatNumber(first + 1)} to ${formatNumber(first + rows.length)} of ${formatNumber(matched)}.`,
  );
  if (panel.rows.length === 0) {
    return <EmptyState title="No rows">Nothing in this table yet.</EmptyState>;
  }
  return (
    <div className="flex flex-col gap-3">
      <TextField
        label={`Filter ${panel.label}`}
        type="search"
        value={words}
        onValueChange={(value) => table.setGlobalFilter(String(value))}
      />
      <p role="status" className={TYPE.note}>
        {count}
      </p>
      {rows.length > 0 && (
        <Table labelledBy={labelledBy}>
          <thead>
            <tr>
              {table.getFlatHeaders().map((header) => {
                const sorted = header.column.getIsSorted();
                return (
                  <th key={header.id} scope="col" aria-sort={sortOf(header.column)}>
                    {/* A small ghost button, 24px tall, its words set back to the column's edge. */}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={header.column.getToggleSortingHandler()}
                      className="-mx-(--button-sm-pad-x) gap-1 text-muted"
                    >
                      {String(header.column.columnDef.header)}
                      <Icon
                        icon={
                          sorted === "asc" ? ArrowUp : sorted === "desc" ? ArrowDown : ArrowUpDown
                        }
                        className="size-3.5"
                      />
                    </Button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} aria-labelledby={`${named}-${row.id}`}>
                {row.getAllCells().map((cell, at) => (
                  <CellOf
                    key={cell.id}
                    cell={cell}
                    {...(at === 0 && { header: `${named}-${row.id}` })}
                  />
                ))}
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {table.getPageCount() > 1 && (
        <fieldset className="m-0 flex min-w-0 items-center gap-2 border-0 p-0">
          <legend className="sr-only">Pages of {panel.label}</legend>
          <Button
            variant="secondary"
            size="sm"
            focusableWhenDisabled
            disabled={!table.getCanPreviousPage()}
            onClick={() => table.previousPage()}
          >
            Previous rows
          </Button>
          <Button
            variant="secondary"
            size="sm"
            focusableWhenDisabled
            disabled={!table.getCanNextPage()}
            onClick={() => table.nextPage()}
          >
            Next rows
          </Button>
        </fieldset>
      )}
    </div>
  );
}
