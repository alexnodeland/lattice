/**
 * A native file read where it is shown, such as in its thread (portalr ADR-0055): a page at a
 * time, as its app rendered it, to page through and see at its own size; and a workbook, whose
 * app renders no page, as its sheets' cells, as its app read them. Neither reads the file itself:
 * a page is the app's PNG, and a sheet is the text the server keeps.
 */

import { ChevronLeft, ChevronRight, Maximize, Minimize } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Button } from "./button";
import { cn } from "./cn";
import { Icon } from "./icon";
import type { PageShown } from "./native-file";
import { ScrollRegion } from "./scroll-region";
import { Skeleton } from "./skeleton";
import { TYPE } from "./type";

/**
 * One page of a file, with the way to the one before and after it and to its own size: the
 * buttons, or the arrow keys, Page Up and Down, Home and End on the page, which in a page read
 * right to left go the other way. Fitted, a page is as tall as the window allows; at its own
 * size, it scrolls.
 */
export function PageViewer({
  label,
  shown,
  total,
  onPage,
}: {
  /** What the pages are of, such as "brief.docx, version 3". */
  label: string;
  shown: PageShown;
  total: number;
  /** Show another page, by its number. */
  onPage: (page: number) => void;
}) {
  const [actual, setActual] = useState(false);
  const { page } = shown;
  const go = (to: number) => onPage(Math.min(total, Math.max(1, to)));
  const keys = useRef<HTMLDivElement>(null);
  const latest = useRef({ page, total, go, actual });
  latest.current = { page, total, go, actual };
  // The keys are heard on the page's box, which is a tab stop, as they bubble from it.
  useEffect(() => {
    const within = keys.current;
    if (within === null) {
      return;
    }
    const heard = (event: KeyboardEvent) => paged(event, within, latest.current);
    within.addEventListener("keydown", heard);
    return () => within.removeEventListener("keydown", heard);
  }, []);
  const name = `Page ${page} of ${total}`;
  return (
    <section aria-label={label} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          aria-label="Previous page"
          disabled={page <= 1}
          onClick={() => go(page - 1)}
        >
          <Icon icon={ChevronLeft} className="size-4 rtl:rotate-180" />
        </Button>
        <p aria-live="polite" className={cn(TYPE.meta, "tabular-nums")}>
          {name}
        </p>
        <Button
          variant="secondary"
          size="sm"
          aria-label="Next page"
          disabled={page >= total}
          onClick={() => go(page + 1)}
        >
          <Icon icon={ChevronRight} className="size-4 rtl:rotate-180" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="ms-auto"
          aria-pressed={actual}
          onClick={() => setActual(!actual)}
        >
          <Icon icon={actual ? Minimize : Maximize} className="size-3.5" />
          Actual size
        </Button>
      </div>
      {/* A tab stop, so the keys page through it, and a keyboard scrolls it at its own size. */}
      <div ref={keys}>
        <ScrollRegion
          aria-label={`${label}: ${name}`}
          className={cn(
            "flex justify-center rounded-md border border-line bg-paper p-2 forced-colors:border-[CanvasText]",
            actual ? "max-h-[80dvh] overflow-auto" : "items-center",
          )}
        >
          {"src" in shown ? (
            <img
              src={shown.src}
              alt={name}
              className={cn(
                "bg-white",
                actual ? "max-w-none" : "max-h-[70dvh] w-auto max-w-full object-contain",
              )}
            />
          ) : shown.state === "reading" ? (
            <Skeleton className="aspect-[1/1.414] h-[min(70dvh,32rem)] max-w-full rounded-sm" />
          ) : (
            <p className="p-6 text-center text-muted text-sm">
              This page couldn't be shown. The file can still be downloaded.
            </p>
          )}
        </ScrollRegion>
      </div>
    </section>
  );
}

/**
 * A key on a page's box, as the viewer pages by it: the other way, by arrow, right to left. A key
 * with a modifier is the browser's, and at its own size the arrows scroll the page, as a
 * scrolled region's do; Page Up and Down, Home and End still page.
 */
function paged(
  event: KeyboardEvent,
  within: Element,
  {
    page,
    total,
    go,
    actual,
  }: { page: number; total: number; go: (to: number) => void; actual: boolean },
) {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.defaultPrevented) {
    return;
  }
  if (actual && event.key.startsWith("Arrow")) {
    return;
  }
  const rtl = getComputedStyle(within).direction === "rtl";
  const step = { ArrowRight: 1, ArrowLeft: -1, PageDown: 1, PageUp: -1 }[event.key];
  if (step !== undefined) {
    go(page + (rtl && event.key.startsWith("Arrow") ? -step : step));
  } else if (event.key === "Home" || event.key === "End") {
    go(event.key === "Home" ? 1 : total);
  } else {
    return;
  }
  event.preventDefault();
}

/** A sheet of a workbook, as its app read it: its name, and its rows of cells' text. */
export interface Sheet {
  readonly name: string;
  readonly rows: readonly (readonly string[])[];
}

/**
 * A workbook's sheets, from the text the server keeps of it: each sheet its name on a line, then a
 * line a row and a tab a cell, the sheets parted by an empty line. A sheet's own empty row is
 * only an empty line if it has one column, so what follows an empty line is a sheet's name only
 * where the outline names that sheet; else, without the outline, every empty line parts sheets.
 * The text has no escapes: a cell holding a tab or a line break is read as two cells, or two rows,
 * which the file itself, downloaded, shows as one.
 */
export function sheetsOf(text: string, named: readonly string[] = []): Sheet[] {
  const sheets: { name: string; rows: string[][] }[] = [];
  const lines = text.split("\n");
  let index = 0;
  while (index < lines.length) {
    const name = lines[index] ?? "";
    const rows: string[][] = [];
    index += 1;
    while (index < lines.length) {
      const line = lines[index] ?? "";
      const next = lines[index + 1];
      const parts =
        line === "" && next !== undefined && (named.length === 0 || named.includes(next));
      if (parts) {
        index += 1;
        break;
      }
      rows.push(line.split("\t"));
      index += 1;
    }
    sheets.push({ name, rows });
  }
  return sheets;
}

/** A column's letters, as a spreadsheet names it: A to Z, then AA. */
export function columnName(index: number): string {
  let name = "";
  for (let left = index + 1; left > 0; left = Math.floor((left - 1) / 26)) {
    name = String.fromCharCode(65 + ((left - 1) % 26)) + name;
  }
  return name;
}

/** The most rows of a sheet shown at once: the file has the rest. */
export const SHOWN_ROWS = 200;

/** The most columns of a sheet shown at once. */
const SHOWN_COLUMNS = 50;

/**
 * A sheet's cells, in a table named by the sheet, its columns lettered and its rows numbered as
 * its app shows them, and scrolled sideways where it is wider than the page. Only the first
 * `SHOWN_ROWS` rows are shown, which it says.
 */
export function SheetTable({ sheet }: { sheet: Sheet }) {
  const caption = useId();
  const shown = sheet.rows.slice(0, SHOWN_ROWS);
  // As wide as the rows shown, up to `SHOWN_COLUMNS`: a wide sheet's cells past it are the file's.
  const wide = shown.reduce((most, row) => Math.max(most, row.length), 0);
  const width = Math.min(wide, SHOWN_COLUMNS);
  // Columns and rows are named by their place, as the app names them: their names are their keys.
  const columns = Array.from({ length: width }, (_, column) => columnName(column));
  const rows = shown.map((cells, line) => ({ number: line + 1, cells }));
  return (
    <div className="flex flex-col gap-2">
      <ScrollRegion
        aria-labelledby={caption}
        className="max-h-[70dvh] overflow-auto rounded-md border border-line"
      >
        <table className="border-collapse text-sm">
          <caption id={caption} className="sr-only">
            {sheet.name}
          </caption>
          <thead className="sticky top-0 bg-wash">
            <tr>
              <th scope="col" className="border-line border-e border-b px-2 py-1">
                <span className="sr-only">Row</span>
              </th>
              {columns.map((column) => (
                <th
                  key={column}
                  scope="col"
                  className="border-line border-e border-b px-2 py-1 text-center font-normal text-muted text-xs"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ number, cells }) => (
              <tr key={number}>
                <th
                  scope="row"
                  className="border-line border-e border-b bg-wash px-2 py-1 text-end font-normal text-muted text-xs tabular-nums"
                >
                  {number}
                </th>
                {columns.map((column, at) => (
                  <td
                    key={column}
                    className="whitespace-pre border-line border-e border-b px-2 py-1 text-fg"
                  >
                    {cells[at] ?? ""}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollRegion>
      {(sheet.rows.length > SHOWN_ROWS || wide > SHOWN_COLUMNS) && (
        <p className={TYPE.note}>
          {[
            sheet.rows.length > SHOWN_ROWS &&
              `The first ${SHOWN_ROWS} of ${sheet.rows.length} rows.`,
            wide > SHOWN_COLUMNS && `The first ${SHOWN_COLUMNS} of ${wide} columns.`,
          ]
            .filter(Boolean)
            .join(" ")}{" "}
          Download the file for the rest.
        </p>
      )}
    </div>
  );
}
