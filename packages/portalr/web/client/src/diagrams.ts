/**
 * A diagram's images, as its canvas moves them (artifactr ADR-0092), in a module of its own, which
 * only the canvas add-on imports, so the first load holds none of it: one a person puts on the
 * canvas is uploaded, a PNG or a JPEG of at most 2 MiB, and named by the digest the server
 * answers with; one the diagram names is read back as a `Blob`, for the canvas to draw. Every
 * route asks for the session and the tenant, so nothing is linked to directly.
 */

import type { Answer } from "./commands";
import type { components as Diagrams } from "./generated/diagrams.openapi";
import { refusalSaid, sentenceOf } from "./reasons";
import { named } from "./rest";
import { type Session, sessionHeaders } from "./session";

/** An image a diagram names: its digest, its size and its type. */
export type DiagramFile = Diagrams["schemas"]["DiagramFile"];

/** The images a canvas takes, which the server takes too. */
export const DIAGRAM_IMAGE_TYPES: readonly string[] = ["image/png", "image/jpeg"];

/** The largest image a canvas takes, in bytes, as the server's limit is. */
export const DIAGRAM_IMAGE_LIMIT = 2 * 1024 * 1024;

/** The most pixels an image's side may be, as the server's limit is. */
export const DIAGRAM_IMAGE_SIDE = 8192;

/** The most pixels an image may be, width times height, as the server's limit is. */
export const DIAGRAM_IMAGE_PIXELS = 4096 * 4096;

const PNG = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
const JPEG = [0xff, 0xd8, 0xff];
/** A JPEG's start-of-frame markers, which hold its size. */
const SOF = new Set([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf]);

const starts = (bytes: Uint8Array, first: readonly number[]) =>
  first.every((byte, at) => bytes[at] === byte);

const word = (bytes: Uint8Array, at: number) => ((bytes[at] ?? 0) << 8) | (bytes[at + 1] ?? 0);

/**
 * An image's width and height, as its header says, read as the server reads it: a PNG's `IHDR`,
 * a JPEG's first frame; or null where its bytes say neither.
 */
export function imageSize(bytes: Uint8Array): { width: number; height: number } | null {
  if (starts(bytes, PNG)) {
    const named = String.fromCharCode(...bytes.subarray(12, 16));
    if (bytes.length < 24 || named !== "IHDR") return null;
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    return { width: view.getUint32(16), height: view.getUint32(20) };
  }
  if (!starts(bytes, JPEG)) return null;
  let at = 2;
  while (at + 4 <= bytes.length) {
    if (bytes[at] !== 0xff) return null;
    const marker = bytes[at + 1] ?? 0;
    if (marker === 0xff) {
      at += 1;
    } else if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd9)) {
      at += 2;
    } else if (SOF.has(marker)) {
      return at + 9 > bytes.length
        ? null
        : { width: word(bytes, at + 7), height: word(bytes, at + 5) };
    } else {
      at += 2 + word(bytes, at + 2);
    }
  }
  return null;
}

/**
 * Why an image can't go on a canvas, in the kit's words, or null where it can: its type, its
 * size, and its pixels as its header says, before any of it is decoded.
 */
export async function imageRefusal(image: Blob): Promise<string | null> {
  if (!DIAGRAM_IMAGE_TYPES.includes(image.type)) return "An image on a canvas is a PNG or a JPEG.";
  if (image.size > DIAGRAM_IMAGE_LIMIT) return "An image on a canvas is at most 2 MiB.";
  // A frame's header is near the start, past what metadata a camera writes: read the first 64
  // KiB, then more where the walk runs off its end, at most the whole image, 2 MiB.
  let size: { width: number; height: number } | null = null;
  for (let read = 65_536; size === null; read *= 8) {
    size = imageSize(new Uint8Array(await image.slice(0, read).arrayBuffer()));
    if (read >= image.size) break;
  }
  if (size === null) return `That isn't a ${image.type === "image/png" ? "PNG" : "JPEG"}.`;
  const { width, height } = size;
  if (width === 0 || height === 0) return "That image has no pixels.";
  if (Math.max(width, height) > DIAGRAM_IMAGE_SIDE || width * height > DIAGRAM_IMAGE_PIXELS) {
    return `An image on a canvas is at most ${DIAGRAM_IMAGE_SIDE} pixels a side, and 4096 by 4096 in all.`;
  }
  return null;
}

/** Where a diagram's images are: whose session, which tenant, workspace and diagram. */
export interface DiagramPlace {
  /** artifactr's surface, beside which the diagrams' routes are mounted, such as `/artifactr/v1`. */
  readonly surface: string;
  readonly session: Session;
  readonly tenant: string;
  readonly workspace: string;
  readonly diagram: string;
}

const imagesOf = (place: DiagramPlace) =>
  `${place.surface.replace(/\/$/, "")}/workspaces/${encodeURIComponent(place.workspace)}` +
  `/diagrams/${encodeURIComponent(place.diagram)}/images`;

const headersOf = (place: DiagramPlace) => ({
  ...sessionHeaders(place.session),
  ...named(place.tenant).headers,
});

/**
 * Upload an image to put on a diagram, after the canvas has checked its type and size. Its
 * answer names the image as the diagram will: by its digest. Refused, it says why.
 */
export async function uploadDiagramImage(
  place: DiagramPlace,
  image: Blob,
): Promise<Answer<DiagramFile>> {
  const refused = await imageRefusal(image);
  if (refused !== null) return { outcome: "refused", status: 0, reasons: [refused] };
  let response: Response;
  try {
    response = await fetch(imagesOf(place), {
      method: "POST",
      headers: { ...headersOf(place), "Content-Type": image.type },
      body: image,
    });
  } catch {
    return {
      outcome: "refused",
      status: 0,
      reasons: ["The connection ended before the server answered."],
    };
  }
  const body: unknown = await response.json().catch(() => null);
  if (response.ok) {
    return { outcome: "done", result: body as DiagramFile };
  }
  const said = await refusalSaid(response.status, body, true).catch(() =>
    sentenceOf(response.status, body, true),
  );
  return { outcome: "refused", status: response.status, reasons: [said] };
}

/**
 * What a person is told of their canvas's edit refused on the stream: the kit's sentence for its
 * rejection's type, never the server's words (portalr ADR-0070).
 */
export function editRefusalSaid(result: unknown): string {
  return sentenceOf(0, result, true);
}

/** A diagram's head, read again: its version and its data, or null where it can't be read. */
export async function readDiagram(
  place: DiagramPlace,
): Promise<{ version: number; data: unknown } | null> {
  const url =
    `${place.surface.replace(/\/$/, "")}/workspaces/${encodeURIComponent(place.workspace)}` +
    `/artifacts/${encodeURIComponent(place.diagram)}`;
  try {
    const response = await fetch(url, { headers: headersOf(place) });
    return response.ok ? ((await response.json()) as { version: number; data: unknown }) : null;
  } catch {
    return null;
  }
}

/**
 * Whether the person may edit the diagram, as grantr answers, asked of the artifact itself: false
 * where it says no or can't be asked, so a canvas offers no edit it would refuse.
 */
export async function mayEditDiagram(
  place: DiagramPlace & { readonly grantr: string },
): Promise<boolean> {
  const resource = { kind: "artifact", workspace: place.workspace, id: place.diagram };
  try {
    const response = await fetch(`${place.grantr.replace(/\/$/, "")}/grantr/v1/checks`, {
      method: "POST",
      headers: { ...headersOf(place), "Content-Type": "application/json" },
      body: JSON.stringify([{ action: "artifactr:edit_artifact", resource }]),
    });
    const answers: unknown = response.ok ? await response.json() : null;
    return Array.isArray(answers) && answers[0] === true;
  } catch {
    return false;
  }
}

/** An image a diagram names, by its digest, or null where it can't be read. */
export async function readDiagramImage(place: DiagramPlace, sha256: string): Promise<Blob | null> {
  try {
    const response = await fetch(`${imagesOf(place)}/${encodeURIComponent(sha256)}`, {
      headers: headersOf(place),
    });
    return response.ok ? await response.blob() : null;
  } catch {
    return null;
  }
}
