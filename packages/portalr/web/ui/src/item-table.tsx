import { type ReactNode, useId } from "react";
import { Card } from "./card";
import { EmptyState } from "./empty-state";
import { Heading } from "./heading";
import { Table } from "./table";

/**
 * One of an item table's columns: its own key, its heading, and what it shows of each item; and,
 * so stacked tables line up, its width, such as "40%".
 */
export interface Column<T> {
  readonly key: string;
  readonly label: string;
  readonly cell: (item: T) => ReactNode;
  readonly width?: string;
}

/**
 * Items as a table from 640 pixels, the breakpoint the app's run lists use, and as a list of
 * cards below, rather than a table scrolled sideways on a phone (portalr ADR-0021). Only one is
 * shown, so only one is in the accessibility tree: the table named by `caption`, or by the
 * heading `labelledBy` names, each row named by its first cell, or the list, named the same, each
 * card headed and named by its first cell, with the others beside their labels and the item's
 * actions last. With no items, it says so. Columns given widths are laid out to them.
 */
export function ItemTable<T>({
  columns,
  items,
  keyOf,
  named,
  actions,
  empty,
  ...naming
}: ({ caption: string } | { labelledBy: string }) & {
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
  const caption = "caption" in naming ? naming.caption : undefined;
  const labelledBy = "labelledBy" in naming ? naming.labelledBy : undefined;
  const fixed = columns.some((column) => column.width !== undefined);
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
        <Table {...naming} className={fixed ? "table-fixed" : undefined}>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key} scope="col" style={{ width: column.width }}>
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
                <th id={id(index, "row")} scope="row">
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
      <ul
        aria-label={caption}
        aria-labelledby={labelledBy}
        className="flex flex-col gap-2 sm:hidden"
      >
        {items.map((item, index) => (
          <li key={keyOf(item)} {...name(item, index, "card")}>
            <Card className="flex flex-col gap-2">
              <Heading id={id(index, "card")} level={3} look="subsection">
                {first.cell(item)}
              </Heading>
              {rest.length > 0 && (
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                  {rest.map((column) => {
                    const cell = column.cell(item);
                    // A card leaves out what an item has nothing for, rather than a label alone.
                    return cell === null || cell === undefined || cell === false ? null : (
                      <div key={column.key} className="contents">
                        <dt className="text-muted">{column.label}</dt>
                        <dd>{cell}</dd>
                      </div>
                    );
                  })}
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
