// The worker's page: Excalidraw's own conversion and export, run in headless Chromium, which the
// server drives (stackr ADR-0049). It loads nothing but its own origin's files, and is told what
// to draw only through `window.diagrams`, which the server calls.

import { convertToExcalidrawElements, exportToSvg, restoreElements } from "@excalidraw/excalidraw";
import type { ExcalidrawElement } from "@excalidraw/excalidraw/element/types";
import type { BinaryFileData, BinaryFiles } from "@excalidraw/excalidraw/types";
import { parseMermaidToExcalidraw } from "@excalidraw/mermaid-to-excalidraw";

/** An element to draw, as artifactr's `Skeleton` sends it. */
export interface Skeleton {
  type: "rectangle" | "ellipse" | "diamond" | "arrow" | "line" | "text" | "frame";
  id?: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  label?: string;
  text?: string;
  stroke_color?: string;
  background_color?: string;
  start?: { id: string };
  end?: { id: string };
}

/** An image a conversion made, as artifactr's `ConvertedFile` reads it. */
export interface Picture {
  media_type: "image/png";
  data: string;
}

/** What a conversion made, as artifactr's `Converted` reads it. */
export interface Converted {
  elements: ExcalidrawElement[];
  files: Record<string, Picture>;
}

/** A diagram to render, as artifactr's `Diagram.to_json` writes it. */
export interface Diagram {
  elements: Record<string, ExcalidrawElement>;
  files: Record<string, { media_type: string }>;
}

/**
 * What a conversion gives: what it made, or why what it was sent can't be drawn. Anything the
 * page throws instead is the worker's failure, not the sender's.
 */
export type Answer = { made: Converted } | { refused: string };

/** What the page offers the server. */
export interface Diagrams {
  mermaid(source: string): Promise<Answer>;
  skeletons(skeletons: Skeleton[]): Promise<Answer>;
  render(diagram: Diagram, files: Record<string, string>, as: "svg" | "png"): Promise<string>;
}

declare global {
  interface Window {
    EXCALIDRAW_ASSET_PATH: string;
    diagrams: Diagrams;
  }
}

// The faces are the worker's own, beside this page: never esm.sh's.
window.EXCALIDRAW_ASSET_PATH = `${location.origin}/`;

type Drawn = NonNullable<Parameters<typeof convertToExcalidrawElements>[0]>;

/**
 * Elements from skeletons, with no link. The agent's skeletons keep the ids it gave them; a
 * Mermaid diagram's are made new, as its nodes' names may be anything.
 */
function converted(drawn: Drawn, regenerateIds: boolean): ExcalidrawElement[] {
  return convertToExcalidrawElements(drawn, { regenerateIds }).map((element) => ({
    ...element,
    // A Mermaid `click` gives an element a link, which an export draws as one: none is kept.
    link: null,
  }));
}

/** An image drawn once, at its own size, as a PNG's base64. */
async function rasterised(url: string): Promise<string> {
  const loaded = new Image();
  loaded.src = url;
  await loaded.decode();
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, loaded.naturalWidth);
  canvas.height = Math.max(1, loaded.naturalHeight);
  const context = canvas.getContext("2d");
  if (context === null) throw new Error("no canvas to draw an image on");
  context.drawImage(loaded, 0, 0);
  const drawn = canvas.toDataURL("image/png");
  return drawn.slice(drawn.indexOf(",") + 1);
}

/** An image, as a PNG: Mermaid's pictures are SVGs, which are drawn once here, and kept as PNGs. */
async function png(file: BinaryFileData): Promise<Picture> {
  return { media_type: "image/png", data: await rasterised(file.dataURL) };
}

async function images(files: BinaryFiles | undefined): Promise<Record<string, Picture>> {
  const made: Record<string, Picture> = {};
  for (const [id, file] of Object.entries(files ?? {})) made[id] = await png(file);
  return made;
}

function skeleton(given: Skeleton): Drawn[number] {
  const drawn: Record<string, unknown> = { type: given.type, x: given.x ?? 0, y: given.y ?? 0 };
  if (given.id !== undefined) drawn.id = given.id;
  if (given.width !== undefined) drawn.width = given.width;
  if (given.height !== undefined) drawn.height = given.height;
  if (given.stroke_color !== undefined) drawn.strokeColor = given.stroke_color;
  if (given.background_color !== undefined) drawn.backgroundColor = given.background_color;
  if (given.type === "text") drawn.text = given.text ?? given.label ?? "";
  else if (given.label !== undefined) drawn.label = { text: given.label };
  if (given.start !== undefined) drawn.start = { id: given.start.id };
  if (given.end !== undefined) drawn.end = { id: given.end.id };
  return drawn as Drawn[number];
}

/**
 * An export's faces, each only as the SVG holds it: a face it couldn't embed, such as Xiaolai
 * while the worker has none, names esm.sh, which a viewer would fetch. It is dropped, and the
 * viewer's own face draws its words.
 */
function held(css: string): string {
  return css.replace(/@font-face\s*\{[^}]*\}/g, (face) =>
    /url\(\s*['"]?(?!data:)/.test(face) ? "" : face,
  );
}

/** Why what was sent can't be drawn, in the words of what refused it. */
function refusal(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

window.diagrams = {
  async mermaid(source) {
    let parsed: Awaited<ReturnType<typeof parseMermaidToExcalidraw>>;
    let elements: ExcalidrawElement[];
    try {
      parsed = await parseMermaidToExcalidraw(source);
      elements = converted(parsed.elements as Drawn, true);
    } catch (error) {
      return { refused: refusal(error) };
    }
    return { made: { elements, files: await images(parsed.files) } };
  },

  async skeletons(skeletons) {
    try {
      return { made: { elements: converted(skeletons.map(skeleton), false), files: {} } };
    } catch (error) {
      return { refused: refusal(error) };
    }
  },

  async render(diagram, files, as) {
    // What a diagram leaves out of an element, Excalidraw's defaults fill, as its canvas does.
    // And a link is drawn as one, out of the SVG: none is kept.
    const elements = restoreElements(Object.values(diagram.elements), null).map((element) => ({
      ...element,
      link: null,
    }));
    const binary: BinaryFiles = {};
    for (const [id, data] of Object.entries(files)) {
      // The server has held each image's type to a PNG's or a JPEG's.
      const mimeType = diagram.files[id]?.media_type ?? "image/png";
      binary[id] = {
        id,
        mimeType,
        dataURL: `data:${mimeType};base64,${data}`,
        created: 0,
      } as BinaryFileData;
    }
    const svg = await exportToSvg({
      elements,
      appState: { exportBackground: true, viewBackgroundColor: "#ffffff", exportEmbedScene: false },
      files: binary,
    });
    for (const style of svg.querySelectorAll("style")) {
      style.textContent = held(style.textContent ?? "");
    }
    const written = new XMLSerializer().serializeToString(svg);
    if (as === "svg") return written;
    // The PNG is the SVG drawn, so the two show the same faces: Excalidraw's own PNG export
    // draws with the document's faces, which this page doesn't load.
    const url = URL.createObjectURL(new Blob([written], { type: "image/svg+xml" }));
    try {
      return await rasterised(url);
    } finally {
      URL.revokeObjectURL(url);
    }
  },
};
