/**
 * What the app knows of a native file before its add-on loads (portalr ADR-0048, ADR-0044): its
 * kinds and their apps, and whether a revision changed its words. The add-on, `on-demand/files`,
 * draws everything else.
 */

import type { IntegrationKey } from "@portalr/client";

/** A native file's app: what people call it, and the integration that switches it. */
export interface Native {
  readonly app: string;
  readonly integration: IntegrationKey;
}

/** A value's fields, if it is an object, or none: a manifest's or a patch's part, read safely. */
export const fields = (value: unknown): Readonly<Record<string, unknown>> =>
  typeof value === "object" && value !== null ? (value as Readonly<Record<string, unknown>>) : {};

/** A manifest's text blob's digest, if it names one. */
const textOf = (data: Readonly<Record<string, unknown>>): string | null => {
  const text = data.text;
  return typeof text === "object" && text !== null && "sha256" in text ? String(text.sha256) : null;
};

/** Whether a revision changed a native file's words: both versions have text, and it differs. */
export function wordsChanged(
  before: Readonly<Record<string, unknown>>,
  after: Readonly<Record<string, unknown>>,
): boolean {
  const [was, is] = [textOf(before), textOf(after)];
  return was !== null && is !== null && was !== is;
}

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
  ["cad_model", { app: "FreeCAD", integration: "files:freecad" }],
  ["scene", { app: "Blender", integration: "files:blender" }],
  ["video_project", { app: "FilmCraft", integration: "files:filmcraft" }],
  ["motion_graphics", { app: "EffectCraft", integration: "files:effectcraft" }],
  ["audio_session", { app: "SoundCraft", integration: "files:soundcraft" }],
]);
