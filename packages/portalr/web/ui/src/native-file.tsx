/**
 * Native files: a Word document, a workbook, a drawing and their kin, kept as a manifest over the file's bytes (lattice
 * RFC-0003). The renderer shows what the manifest holds, the name, type, size, pages and outline,
 * and changes are read from the outline; the app adds what it reads from the server, the pages
 * and who has the file, through `file-pages`' parts (portalr ADR-0048).
 */

import { useId } from "react";
import { capped, type Data, type Renderer } from "./artifacts";

/** What people call a native file's type, by its media type. */
const TYPES: Readonly<Record<string, string>> = {
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Workbook",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": "Presentation",
  "application/pdf": "PDF document",
  "image/vnd.dxf": "Drawing (DXF)",
  "image/vnd.dwg": "Drawing (DWG)",
  "image/vnd.adobe.photoshop": "Layered image",
  "image/svg+xml": "Vector image",
  "application/vnd.adobe.indesign-idml-package": "Page layout",
  "application/x-figcraft": "Design",
  "application/x-extension-fcstd": "3D model",
  "application/x-blender": "3D scene",
  "application/x-fcproj": "Video project",
  "application/x-ecproj": "Motion graphics",
  "application/x-scraft": "Audio session",
};

const UNITS = ["bytes", "kB", "MB", "GB"] as const;

/** A size in bytes as people read it, in powers of a thousand: "48 kB", "1.2 MB". */
export function fileSize(bytes: number): string {
  let size = bytes;
  let unit = 0;
  const shown = () => (unit === 0 || size >= 10 ? Math.round(size) : Math.round(size * 10) / 10);
  // Moved up a unit while its figure, as it is shown, would reach a thousand: 999,950 bytes is
  // "1 MB", not "1000 kB".
  while (shown() >= 1000 && unit < UNITS.length - 1) {
    size /= 1000;
    unit += 1;
  }
  return `${shown()} ${UNITS[unit]}`;
}

/** What a manifest says of its file, read without trusting its shape. */
export interface FileFacts {
  readonly name: string;
  readonly type: string;
  readonly size: number | null;
  readonly pages: number | null;
  readonly outline: string;
}

const text = (value: unknown) => (typeof value === "string" ? value : "");
const count = (value: unknown) =>
  typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;

/** A native file's facts, from its manifest: what's missing or malformed is left out. */
export function factsOf(data: Data): FileFacts {
  const content =
    typeof data.content === "object" && data.content !== null
      ? (data.content as Readonly<Record<string, unknown>>)
      : {};
  const mediaType = text(content.media_type);
  return {
    name: text(data.name),
    type: TYPES[mediaType] ?? (mediaType || "File"),
    size: count(content.size),
    pages: count(data.pages),
    outline: text(data.outline),
  };
}

/** A native file's name, type, size, pages and outline. */
function Summary({ facts }: { facts: FileFacts }) {
  const outline = useId();
  // An outline's lines can repeat, so each is keyed by its text and how often it came before.
  const seen = new Map<string, number>();
  const lines = facts.outline
    .split("\n")
    .filter((line) => line.trim() !== "")
    .map((line) => {
      const before = seen.get(line) ?? 0;
      seen.set(line, before + 1);
      return { line, key: `${line}#${before}` };
    });
  const about = [
    facts.type,
    facts.size === null ? null : fileSize(facts.size),
    facts.pages === null ? null : `${facts.pages} ${facts.pages === 1 ? "page" : "pages"}`,
  ].filter(Boolean);
  return (
    <div className="flex flex-col gap-3">
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="break-all font-mono font-semibold text-fg text-sm">
          {facts.name || "Unnamed file"}
        </span>
        <span className="text-muted text-sm">{about.join(" · ")}</span>
      </p>
      {lines.length > 0 ? (
        // Not a heading: a renderer doesn't know how deep in its page it is drawn.
        <section aria-labelledby={outline} className="flex flex-col gap-1">
          <span id={outline} className="font-semibold text-muted text-xs uppercase tracking-wide">
            Outline
          </span>
          <ol className="flex flex-col gap-0.5 border-line border-l-2 pl-3 text-fg text-sm">
            {lines.map(({ line, key }) => (
              <li key={key}>{line}</li>
            ))}
          </ol>
        </section>
      ) : (
        <p className="text-muted text-sm italic">The app read no outline from this file.</p>
      )}
    </div>
  );
}

/**
 * The renderer for a native file's kind, such as `word_document`: its manifest shown, its title
 * its file's name, and its changes read from its outline, line by line, as the RFC has it; the
 * file's own words are compared by the app, from the text the server keeps.
 */
export function nativeFile(): Renderer {
  return {
    render: (data) => <Summary facts={factsOf(data)} />,
    text: (data) => factsOf(data).outline,
    parts: (data) => [
      { name: "contents", text: factsOf(data).outline, diff: "lines", language: "text" },
    ],
    title: (data) => capped(factsOf(data).name),
    diff: "lines",
    inline: true,
  };
}
