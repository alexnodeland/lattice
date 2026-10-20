/**
 * A native file in the thread it was made in (portalr ADR-0055): read there, a page at a time as
 * its app rendered it, or, for a workbook, whose app renders none, as its sheets' cells; its
 * outline and its words beside; a download; and who has it, with checking it out and in, or its
 * editor framed here where its app's build hands the file over. Every read is the server's, as
 * the person viewing it: the page never parses the file.
 */

import { Refused } from "@portalr/client";
import {
  Alert,
  fileSize,
  PageViewer,
  Reading,
  ScrollRegion,
  SegmentedFilter,
  SheetTable,
  sheetsOf,
} from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import type { Place } from "./check-out";
import { DownloadButton, FileControls, type Native, useDownload } from "./native-file";

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

type View = "pages" | "sheets" | "outline" | "text";

const VIEWS: Readonly<Record<View, string>> = {
  pages: "Pages",
  sheets: "Cells",
  outline: "Outline",
  text: "Text",
};

/** The sheets an outline names, each a line of its own, without the range it uses. */
const sheetNames = (outline: string): string[] =>
  outline
    .split("\n")
    .filter((line) => line !== "" && !line.startsWith(" "))
    .map((line) => line.replace(/ \([A-Z]+[0-9]+(?::[A-Z]+[0-9]+)?\)$/, ""));

/** An outline's lines with words, each keyed by its text and how often it came before. */
function outlined(outline: string) {
  const seen = new Map<string, number>();
  return outline
    .split("\n")
    .filter((line) => line.trim() !== "")
    .map((line) => {
      const before = seen.get(line) ?? 0;
      seen.set(line, before + 1);
      return { line, key: `${line}#${before}` };
    });
}

/** A version's words, as the server keeps them, read once asked for. */
function useWords(place: Place, version: number) {
  const { context, tenant, workspace, artifact } = place;
  return useQuery(context.queries.files.text(tenant, workspace, artifact, version));
}

/** A version's text, read: what it says while it is read, or why it isn't there. */
function Words({
  place,
  version,
  children,
}: {
  place: Place;
  version: number;
  children: (text: string) => ReactNode;
}) {
  const read = useWords(place, version);
  if (read.isError) {
    return <Alert tone="error">Its words couldn't be read. Try again in a moment.</Alert>;
  }
  if (read.data === undefined) {
    return <Reading>Reading its words…</Reading>;
  }
  if (read.data === null) {
    return <p className="text-muted text-sm italic">The app read no words from this file.</p>;
  }
  return children(read.data);
}

/** A version's pages, one at a time: the one shown, read as it is asked for. */
function Pages({
  place,
  version,
  total,
  name,
}: {
  place: Place;
  version: number;
  total: number;
  name: string;
}) {
  const { context, tenant, workspace, artifact } = place;
  const [wanted, setWanted] = useState(1);
  // A version with fewer pages than the one before shows its last.
  const page = Math.min(wanted, total);
  const read = useQuery(context.queries.files.page(tenant, workspace, artifact, version, page));
  return (
    <PageViewer
      label={`${name}, version ${version}`}
      shown={
        read.data !== undefined
          ? { page, src: read.data }
          : { page, state: read.isError ? "failed" : "reading" }
      }
      total={total}
      onPage={setWanted}
    />
  );
}

/** A workbook's sheets, one at a time, chosen by name where it has more than one. */
function Sheets({ text, outline }: { text: string; outline: string }) {
  const sheets = sheetsOf(text, sheetNames(outline));
  const [chosen, setChosen] = useState("0");
  const index = Math.min(Number(chosen), sheets.length - 1);
  const sheet = sheets[index];
  if (sheet === undefined) {
    return <p className="text-muted text-sm italic">This workbook has no sheets to show.</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      {sheets.length > 1 && (
        <SegmentedFilter
          label="Sheet"
          segments={sheets.map((each, at) => ({ value: String(at), label: each.name }))}
          value={String(index)}
          onValueChange={setChosen}
        />
      )}
      <SheetTable sheet={sheet} />
    </div>
  );
}

/**
 * A native file, inline: what it is, a view of it, its download, and what the reader can do with
 * it. Where native files' routes aren't served, `unserved` is shown instead: the manifest alone.
 */
export function NativeInline({
  place,
  native,
  me,
  unserved,
}: {
  place: Place;
  native: Native;
  me: string;
  unserved: ReactNode;
}) {
  const { context, tenant, workspace, artifact } = place;
  const { data: status, error } = useQuery(
    context.queries.files.status(tenant, workspace, artifact),
  );
  const { saving, download } = useDownload(place, status?.name);
  const [chosen, setChosen] = useState<View | null>(null);
  if (error instanceof Refused && error.status === 404) {
    return unserved;
  }
  if (status === undefined) {
    return error === null ? (
      <Reading>Reading the file…</Reading>
    ) : (
      <Alert tone="error">
        This file couldn't be read: its pages, and who has it. Reload the page to try again.
      </Alert>
    );
  }
  const pages = status.pages ?? 0;
  const views: View[] = [
    ...(pages > 0 ? (["pages"] as const) : []),
    ...(status.media_type === XLSX ? (["sheets"] as const) : []),
    "outline",
    "text",
  ];
  const view = chosen !== null && views.includes(chosen) ? chosen : (views[0] ?? "outline");
  const about = [
    fileSize(status.size),
    pages > 0 ? `${pages} ${pages === 1 ? "page" : "pages"}` : null,
    `version ${status.version}`,
  ].filter(Boolean);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {/* Its name is the entry's, above. */}
        <p className="text-muted text-sm">{about.join(" · ")}</p>
        <DownloadButton saving={saving} onDownload={() => void download(status.version)} />
      </div>
      <SegmentedFilter
        label={`Show ${status.name} as`}
        segments={views.map((each) => ({ value: each, label: VIEWS[each] }))}
        value={view}
        onValueChange={setChosen}
      />
      {view === "pages" && (
        <Pages place={place} version={status.version} total={pages} name={status.name} />
      )}
      {view === "sheets" && (
        <Words place={place} version={status.version}>
          {(text) => <Sheets text={text} outline={status.outline} />}
        </Words>
      )}
      {view === "outline" &&
        (status.outline.trim() === "" ? (
          <p className="text-muted text-sm italic">The app read no outline from this file.</p>
        ) : (
          <ol
            aria-label={`Outline of ${status.name}`}
            className="flex flex-col gap-0.5 border-line border-s-2 ps-3 text-fg text-sm"
          >
            {outlined(status.outline).map(({ line, key }) => (
              <li key={key} className="whitespace-pre-wrap">
                {line}
              </li>
            ))}
          </ol>
        ))}
      {view === "text" && (
        <Words place={place} version={status.version}>
          {(text) => (
            <ScrollRegion
              aria-label={`Text of ${status.name}`}
              className="max-h-[70dvh] overflow-y-auto rounded-md border border-line bg-paper p-3"
            >
              <p className="whitespace-pre-wrap break-words text-fg text-sm">{text}</p>
            </ScrollRegion>
          )}
        </Words>
      )}
      <FileControls
        place={place}
        native={native}
        me={me}
        status={status}
        onDownload={download}
        saving={saving}
      />
    </div>
  );
}
