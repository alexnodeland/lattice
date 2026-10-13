import { type ReactNode, useId } from "react";
import { Card } from "./card";
import { EmptyState } from "./empty-state";
import { Table } from "./table";

/** One of an item table's columns: its own key, its heading, and what it shows of each item. */
export interface Column<T> {
  readonly key: string;
  readonly label: string;
  readonly cell: (item: T) => ReactNode;
}

/**
 * Items as a table from 640 pixels, the breakpoint the app's run lists use, and as a list of
 * cards below, rather than a table scrolled sideways on a phone (portalr ADR-0021). Only one is
 * shown, so only one is in the accessibility tree: the table named by `caption`, each row named
 * by its first cell, or the list, named the same, each card headed and named by its first cell,
 * with the others beside their labels and the item's actions last. With no items, it says so.
 */
export function ItemTable<T>({
  caption,
  columns,
  items,
  keyOf,
  named,
  actions,
  empty,
}: {
  caption: string;
  columns: readonly [Column<T>, ...Column<T>[]];
  items: readonly T[];
  keyOf: (item: T) => string;
  /** Each item's name, where its first cell alone doesn't say which it is. */
  named?: ((item: T) => string) | undefined;
  /** What can be done with an item, such as removing it, in its last cell or at its card's end. */
  actions?: ((item: T) => ReactNode) | undefined;
  /** What shows when there are no items: a title, and what will appear. */
  empty: { readonly title: string; readonly body: ReactNode };
}) {
  const prefix = useId();
  if (items.length === 0) {
    return <EmptyState title={empty.title}>{empty.body}</EmptyState>;
  }
  const [first, ...rest] = columns;
  /** A row's or card's name: `named`'s, or its first cell's. */
  const name = (item: T, index: number, where: string) =>
    named ? { "aria-label": named(item) } : { "aria-labelledby": id(index, where) };
  const id = (index: number, where: string) => `${prefix}-${where}-${index}`;
  return (
    <>
      <div className="max-sm:hidden">
        <Table caption={caption}>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key} scope="col">
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
            {items.map((item, index) => (
              <tr key={keyOf(item)} {...name(item, index, "row")}>
                <th id={id(index, "row")} scope="row" className="font-semibold text-fg">
                  {first.cell(item)}
                </th>
                {rest.map((column) => (
                  <td key={column.key}>{column.cell(item)}</td>
                ))}
                {actions && <td className="text-right">{actions(item)}</td>}
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
      <ul aria-label={caption} className="flex flex-col gap-2 sm:hidden">
        {items.map((item, index) => (
          <li key={keyOf(item)} {...name(item, index, "card")}>
            <Card className="flex flex-col gap-2">
              <h3 id={id(index, "card")} className="font-semibold">
                {first.cell(item)}
              </h3>
              {rest.length > 0 && (
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                  {rest.map((column) => (
                    <div key={column.key} className="contents">
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
