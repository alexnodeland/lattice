/** A Word document's manifest and pages, for the native file's tests and its screenshots. */

import type { PageShown } from "../file-pages";

export const MANIFEST = {
  name: "launch-brief.docx",
  content: {
    sha256: "a".repeat(64),
    size: 48_213,
    media_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  },
  fingerprint: "b".repeat(64),
  text: { sha256: "c".repeat(64), size: 912, media_type: "text/plain; charset=utf-8" },
  review: null,
  outline: "Launch brief\nWho comes\nWhat to bring\nWho comes",
  pages: 4,
  provenance: { source: "check_in", base: "d".repeat(64) },
} as const;

/** A page as an app renders one: paper, a heading and lines of text, drawn, as a `data:` URL. */
function page(lines: number, heading: number): string {
  const bars = Array.from(
    { length: lines },
    (_, line) =>
      `<rect x="40" y="${110 + line * 26}" width="${line % 4 === 3 ? 320 : 515}" height="10" fill="#9ca3af"/>`,
  ).join("");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="595" height="842"><rect width="595" height="842" fill="#fff"/><rect x="40" y="56" width="${heading}" height="22" fill="#374151"/>${bars}</svg>`;
  return `data:image/svg+xml;base64,${btoa(svg)}`;
}

/** The first three of four pages: two shown, one being read; and one that couldn't be. */
export const PAGES: readonly PageShown[] = [
  { page: 1, src: page(24, 260) },
  { page: 2, src: page(18, 180) },
  { page: 3, state: "reading" },
];

export const FAILED: readonly PageShown[] = [{ page: 1, state: "failed" }];

/** A check-out's expiry, on the day `NOW` is. */
export const UNTIL = "2026-10-17T17:30:00Z";
export const NOW = new Date("2026-10-17T09:30:00Z");
