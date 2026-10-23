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
  IconButton,
  PageViewer,
  Reading,
  ScrollRegion,
  SegmentedFilter,
  SheetTable,
  sheetsOf,
} from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { editorAt, type Place } from "./check-out";
import { useEditing } from "./editing";
import { downloadingSaid, FileControls, type Native, useDownload } from "./native-file";
import { useNear } from "./near";
import { ViewSlotsContext } from "./view-slots";

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
  // Read once for each text: a workbook's can be long, and the page renders on every poll.
  const sheets = useMemo(() => sheetsOf(text, sheetNames(outline)), [text, outline]);
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
export function NativeInline(props: {
  place: Place;
  native: Native;
  me: string;
  unserved: ReactNode;
  /** The entry's header, where its download goes once the file is read. */
  header?: HTMLElement | null;
}) {
  const box = useRef<HTMLDivElement>(null);
  const { near, seen } = useNear(box);
  return (
    <div ref={box} className="min-h-12">
      <FileView {...props} near={near} seen={seen} />
    </div>
  );
}

function FileView({
  place,
  native,
  me,
  unserved,
  header = null,
  near,
  seen,
}: {
  place: Place;
  native: Native;
  me: string;
  unserved: ReactNode;
  header?: HTMLElement | null;
  near: boolean;
  seen: boolean;
}) {
  const { context, tenant, workspace, artifact } = place;
  const reads = context.queries.files.status(tenant, workspace, artifact);
  // Read once it comes near the window, and polled only while it is near.
  const { data: status, error } = useQuery({
    ...reads,
    enabled: seen,
    refetchInterval: (near && reads.refetchInterval) || false,
  });
  const { saving, download } = useDownload(place, status?.name);
  const [chosen, setChosen] = useState<View | null>(null);
  // One box for the file: its preview, or, while it is edited here, its editor, flipped in place.
  const editing = useEditing()?.artifact === artifact;
  const [viewport, setViewport] = useState<HTMLElement | null>(null);
  const [toggle, setToggle] = useState<HTMLElement | null>(null);
  const slots = useMemo(() => ({ viewport, toggle }), [viewport, toggle]);
  // A flip turns, and moves the focus to the side turned to; the box's first drawing doesn't.
  const preview = useRef<HTMLDivElement>(null);
  const was = useRef(editing);
  const [turned, setTurned] = useState(false);
  useEffect(() => {
    if (was.current === editing) {
      return;
    }
    was.current = editing;
    setTurned(true);
    (editing ? viewport : preview.current)?.focus();
  }, [editing, viewport]);
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
  // Its build hands the file over and its editor is hosted: the box flips between the two.
  const editable =
    status.talk === "bridged" && editorAt(context.config.editors, native.integration) !== null;
  const about = [
    fileSize(status.size),
    pages > 0 ? `${pages} ${pages === 1 ? "page" : "pages"}` : null,
    `version ${status.version}`,
  ].filter(Boolean);
  // Its download is the header's, beside its page: the file's head, as its status reads it now,
  // offered only once the file is read and served. A failure is said below, in its controls, and
  // announced beside the button, since a tall preview can put what is said below out of sight.
  const downloading = saving === "saving";
  const downloadButton = (
    <>
      <IconButton
        label="Download"
        icon={Download}
        aria-busy={downloading || undefined}
        disabled={downloading}
        focusableWhenDisabled
        onClick={() => void download(status.version)}
      />
      <span role="status" className="sr-only">
        {saving === "failed" ? `${status.name} wasn't downloaded.` : downloadingSaid(saving)}
      </span>
    </>
  );
  return (
    <div className="flex flex-col gap-3">
      {header && createPortal(downloadButton, header)}
      {/* Its name and its download are the entry's header's, above. */}
      <p className="text-muted text-sm">{about.join(" · ")}</p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {editing ? (
          <p className="text-muted text-sm">Editing in {native.app}</p>
        ) : (
          <SegmentedFilter
            label={`Show ${status.name} as`}
            segments={views.map((each) => ({ value: each, label: VIEWS[each] }))}
            value={view}
            onValueChange={setChosen}
          />
        )}
        <span ref={setToggle} className="ms-auto empty:hidden" />
      </div>
      <div className={editable ? "h-[min(80dvh,48rem)]" : undefined}>
        {/* Hidden, not taken down, while it is edited: its page, its zoom and its view are kept. */}
        <section
          ref={preview}
          hidden={editing}
          tabIndex={-1}
          aria-label={`Preview of ${status.name}`}
          className={`flex flex-col gap-3 outline-none ${turned ? "flip-in" : ""} ${editable ? "h-full overflow-auto" : ""}`}
        >
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
                  className="max-h-[70dvh] overflow-y-auto rounded-(--code-block-radius) border border-line bg-paper p-3"
                >
                  <p className="whitespace-pre-wrap break-words text-fg text-sm">{text}</p>
                </ScrollRegion>
              )}
            </Words>
          )}
        </section>
        <section
          ref={setViewport}
          hidden={!editing}
          tabIndex={-1}
          aria-label={`${status.name} in ${native.app}`}
          className={`h-full outline-none ${turned ? "flip-in" : ""}`}
        />
      </div>
      <ViewSlotsContext value={slots}>
        <FileControls
          place={place}
          native={native}
          me={me}
          status={status}
          onDownload={download}
          saving={saving}
        />
      </ViewSlotsContext>
    </div>
  );
}
