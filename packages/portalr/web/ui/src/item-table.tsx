import type { ReactNode } from "react";
import { Card } from "./card";
import { Table } from "./table";

/** One of an item table's columns: its heading, and what it shows of each item. */
export interface Column<T> {
  readonly label: string;
  readonly cell: (item: T) => ReactNode;
}

/**
 * Items as a table from 768 pixels, and as a list of cards below, rather than a table scrolled
 * sideways on a phone (portalr ADR-0021). Only one is shown, so only one is in the accessibility
 * tree: the table named by `caption`, or the list, named the same. Each card is headed by the
 * first column, with the others beside their labels, and the item's actions last.
 */
export function ItemTable<T>({
  caption,
  columns,
  items,
  keyOf,
  actions,
  empty,
}: {
  caption: string;
  columns: readonly [Column<T>, ...Column<T>[]];
  items: readonly T[];
  keyOf: (item: T) => string;
  /** What can be done with an item, such as removing it, in its last cell or at its card's end. */
  actions?: (item: T) => ReactNode;
  /** What shows when there are no items. */
  empty: ReactNode;
}) {
  if (items.length === 0) {
    return <p className="text-muted text-sm">{empty}</p>;
  }
  const [first, ...rest] = columns;
  return (
    <>
      <div className="max-md:hidden">
        <Table caption={caption}>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.label} scope="col">
                  {column.label}
                </th>
              ))}
              {actions && (
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={keyOf(item)}>
                <th scope="row" className="font-semibold text-fg">
                  {first.cell(item)}
                </th>
                {rest.map((column) => (
                  <td key={column.label}>{column.cell(item)}</td>
                ))}
                {actions && <td className="text-right">{actions(item)}</td>}
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
      <ul aria-label={caption} className="flex flex-col gap-2 md:hidden">
        {items.map((item) => (
          <li key={keyOf(item)}>
            <Card className="flex flex-col gap-2">
              <p className="font-semibold">{first.cell(item)}</p>
              {rest.length > 0 && (
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                  {rest.map((column) => (
                    <div key={column.label} className="contents">
                      <dt className="text-muted">{column.label}</dt>
                      <dd>{column.cell(item)}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {actions && <div className="flex flex-wrap gap-2">{actions(item)}</div>}
            </Card>
          </li>
        ))}
      </ul>
    </>
  );
}
