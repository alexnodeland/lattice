/**
 * How the app shows each artifact kind it knows (portalr ADR-0017): the template's `note`, whose
 * Markdown is in its `text`, artifactr.ui's forms, submissions, dashboards and apps (lattice
 * RFC-0005), and a native file's kinds, whose manifests name a file's bytes (portalr ADR-0048).
 * Any other kind shows as JSON.
 */

import { markdown, nativeFile, type Renderers, UI_RENDERERS } from "@portalr/ui";
import type { Native } from "./native-file";

/**
 * The native files' kinds, each with its app: what people call it, and the integration that
 * switches it in a workspace. Off, a file is read and downloaded, and nothing more.
 */
export const NATIVE: ReadonlyMap<string, Native> = new Map([
  ["word_document", { app: "WordCraft", integration: "files:wordcraft" }],
  ["workbook", { app: "GridCraft", integration: "files:gridcraft" }],
  ["presentation", { app: "DeckCraft", integration: "files:deckcraft" }],
  ["pdf_document", { app: "PdfCraft", integration: "files:pdfcraft" }],
  ["drawing", { app: "CADCraft", integration: "files:cadcraft" }],
  ["layered_image", { app: "PhotoCraft", integration: "files:photocraft" }],
  ["vector_image", { app: "VectorCraft", integration: "files:vectorcraft" }],
  ["page_layout", { app: "DesignCraft", integration: "files:designcraft" }],
  ["design", { app: "FigCraft", integration: "files:figcraft" }],
]);

export const RENDERERS: Renderers = new Map([
  ["note", markdown()],
  ...[...NATIVE.keys()].map((kind) => [kind, nativeFile()] as const),
  ...UI_RENDERERS,
]);
