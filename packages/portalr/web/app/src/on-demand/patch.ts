/**
 * A diagram's edit, as the canvas sends it: the patch artifactr's `element_patch` writes, ported,
 * and held to it by one fixture, which artifactr's tests write and both sides check
 * (`packages/artifactr/schemas/excalidraw_patches.json`, portalr ADR-0074). Every writer, person
 * or agent, sends one shape: each changed element replaced whole after a `test` of the version it
 * had, a new one added, a deleted one marked `isDeleted`, never removed, and a new image added
 * under its digest. And `rebase`, as artifactr's, moves a person's edit onto a head that moved on.
 */

/** An element, as JSON: Excalidraw's, with whatever fields it holds. */
export type ElementJson = Readonly<Record<string, unknown>> & {
  readonly id: string;
  readonly version: number;
  readonly versionNonce: number;
};

/** An image a diagram names: its digest, its size and its type. */
export interface FileJson {
  readonly sha256: string;
  readonly size: number;
  readonly media_type: string;
}

/** What a patch is made from: a diagram's elements and images, by id and by digest. */
export interface Scene {
  readonly elements: Readonly<Record<string, ElementJson>>;
  readonly files: Readonly<Record<string, FileJson>>;
}

/** One operation of a JSON Patch, as artifactr takes it. */
export type Op =
  | { readonly op: "test"; readonly path: string; readonly value: number }
  | { readonly op: "replace" | "add"; readonly path: string; readonly value: unknown };

/** An element as artifactr writes it: with the fields its model always holds, filled. */
function json(element: ElementJson): Record<string, unknown> {
  return { isDeleted: false, index: null, updated: null, ...element };
}

/** JSON with its keys sorted, at every depth: one text for one value. */
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (typeof value === "object" && value !== null) {
    const fields = Object.entries(value)
      .filter(([, each]) => each !== undefined)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return `{${fields.map(([key, each]) => `${JSON.stringify(key)}:${canonical(each)}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

/** Whether two elements are written alike: artifactr's `Element.written`. */
const same = (a: ElementJson, b: ElementJson) => canonical(json(a)) === canonical(json(b));

const at = (key: string) => `/elements/${key}`; // an element's id has no "/" or "~" to escape

/**
 * The patch that takes `base` to `elements`, and adds the `files` it doesn't have: an element
 * that differs replaced after a test of its version in `base`, one `base` hasn't added; one
 * `elements` leaves out kept. Empty, nothing changed, which artifactr refuses: it isn't sent.
 */
export function elementPatch(
  base: Scene,
  elements: Readonly<Record<string, ElementJson>>,
  files: Readonly<Record<string, FileJson>> = {},
): Op[] {
  const ops: Op[] = [];
  for (const [key, element] of Object.entries(elements)) {
    const before = base.elements[key];
    if (before === undefined) {
      ops.push({ op: "add", path: at(key), value: json(element) });
    } else if (!same(before, element)) {
      ops.push({ op: "test", path: `${at(key)}/version`, value: before.version });
      ops.push({ op: "replace", path: at(key), value: json(element) });
    }
  }
  for (const [digest, file] of Object.entries(files)) {
    if (!(digest in base.files)) {
      ops.push({ op: "add", path: `/files/${digest}`, value: { ...file } });
    }
  }
  return ops;
}

/** Whether the local element wins over the remote one, as Excalidraw 0.18.1 decides. */
export function won(local: ElementJson, remote: ElementJson): boolean {
  if (local.version !== remote.version) return local.version > remote.version;
  return local.versionNonce < remote.versionNonce;
}

/**
 * A new nonce, as Excalidraw makes one, a 31-bit integer, but never 0: each as likely, a draw
 * of 31 bits drawn again where it is 0, never a remainder.
 */
function nonce(): number {
  const drawn = new Uint32Array(1);
  for (;;) {
    crypto.getRandomValues(drawn);
    const value = (drawn[0] ?? 0) >>> 1; // 0 to 2 ** 31 - 1, each as likely
    if (value !== 0) return value;
  }
}

/**
 * A person's elements, made from `base`, moved onto `head` after a version conflict: where an
 * element they changed wins over the head's, it is sent again at one version above the head's (or
 * its own, if higher), with a new nonce; where the head's wins, their change is dropped.
 */
export function rebase(
  base: Scene,
  local: Readonly<Record<string, ElementJson>>,
  head: Scene,
): Record<string, ElementJson> {
  const merged: Record<string, ElementJson> = { ...head.elements };
  for (const [key, element] of Object.entries(local)) {
    const before = base.elements[key];
    if (before !== undefined && same(before, element)) continue;
    const theirs = head.elements[key];
    if (theirs === undefined) {
      merged[key] = element;
    } else if (won(element, theirs)) {
      merged[key] = {
        ...element,
        version: Math.max(element.version, theirs.version + 1),
        versionNonce: nonce(),
      };
    }
  }
  return merged;
}
