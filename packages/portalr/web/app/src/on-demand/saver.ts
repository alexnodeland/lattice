/**
 * How a person's canvas saves (portalr ADR-0074, artifactr ADR-0088's cadence): an edit is sent
 * when they let go of what they drew, or after two seconds of quiet, and at most once every five
 * seconds; one at a time. Each is the element-scoped patch every writer sends (`patch.ts`), against
 * the version they last saved on. Applied, that version moves on; stale, their edit is moved onto
 * the head and sent again, three times at most, then kept until the next revision arrives;
 * proposed or refused, the canvas stops saving and says why. From a change until it is saved, the
 * canvas says "Saving…". When it closes, what isn't saved is sent. A revision someone else saved,
 * drawn on the canvas as it arrives, is what the next save is an edit of.
 */

import type { Committed } from "./canvas-host";
import {
  type ElementJson,
  elementPatch,
  type FileJson,
  type Op,
  rebase,
  type Scene,
} from "./patch";

/** The most elements a diagram holds, deleted ones included (artifactr ADR-0086). */
export const MAX_ELEMENTS = 2_000;

/** The most bytes of JSON a diagram is (artifactr ADR-0086). */
const MAX_BYTES = 1024 * 1024;

/** How long the canvas waits for quiet before it saves. */
export const QUIET = 2_000;

/** The least time between two saves of a person's. */
export const EVERY = 5_000;

/** A diagram's version, and its elements and images then. */
export interface Saved {
  readonly version: number;
  readonly scene: Scene;
}

/** What the canvas saves through: a person's edit, and the diagram's head, to move it onto. */
export interface Saving {
  commit(edit: { baseVersion: number; ops: readonly Op[]; summary: string }): Promise<Committed>;
  head(): Promise<Saved | null>;
}

/** What the canvas says of its saving, or null for nothing. */
export type Said =
  | { readonly state: "saving" | "saved" }
  | { readonly state: "stopped"; readonly text: string }
  | null;

/** How often an edit is moved onto a head that moved on before it waits for the next revision. */
const MOVES = 3;

/**
 * A head as what an edit is of: an element no one changed held as the canvas drew it, so it isn't
 * sent again. One Excalidraw changed as it drew it, such as one it gave an order to, is sent
 * again, tested at the head's version, which it is.
 */
function onto(head: Saved, drawn: Readonly<Record<string, ElementJson>>): Saved {
  const held: Record<string, ElementJson> = { ...head.scene.elements };
  for (const [key, element] of Object.entries(drawn)) {
    const theirs = held[key];
    if (theirs?.version === element.version && theirs.versionNonce === element.versionNonce) {
      held[key] = element;
    }
  }
  return { version: head.version, scene: { ...head.scene, elements: held } };
}

/** What a save's patch changes, said for its revision. */
export function summary(ops: readonly Op[]): string {
  const changed = new Set(
    ops.filter((op) => op.path.startsWith("/elements/")).map((op) => op.path.split("/")[2]),
  ).size;
  const images = ops.filter((op) => op.path.startsWith("/files/")).length;
  const said = [`${changed} ${changed === 1 ? "element" : "elements"} changed on the canvas`];
  if (images > 0) said.push(`${images} ${images === 1 ? "image" : "images"} added`);
  return said.join(", ");
}

const bytes = (scene: Scene) => new TextEncoder().encode(JSON.stringify(scene)).length;

/** The clock and the timers a saver waits by: the window's, unless a test gives its own. */
export interface Clock {
  now(): number;
  after(ms: number, then: () => void): () => void;
}

const WINDOW: Clock = {
  now: () => Date.now(),
  after: (ms, then) => {
    const timer = setTimeout(then, ms);
    return () => clearTimeout(timer);
  },
};

export class Saver {
  #base: Saved;
  readonly #saving: Saving;
  readonly #read: () => Scene;
  readonly #said: (said: Said) => void;
  readonly #moved: (
    elements: Record<string, ElementJson>,
    files: Readonly<Record<string, FileJson>>,
  ) => Record<string, ElementJson>;
  readonly #clock: Clock;
  #cancel: (() => void) | null = null;
  #sentAt = Number.NEGATIVE_INFINITY;
  #inFlight = false;
  #dirty = false;
  #stopped = false;
  #closing = false;
  /** An edit that moved onto a head too often, kept to send with the next revision. */
  #parked = false;
  #saidLast: string | null = null;
  /** What was drawn after a move onto the head: what the next save sends, not a read. */
  #drawn: Scene | null = null;

  /**
   * @param base The version the canvas opened on.
   * @param saving Where it saves.
   * @param read The canvas's elements and images now, as a diagram holds them.
   * @param said Told what the canvas says of its saving.
   * @param moved Told the elements to draw after an edit was moved onto a head that moved on;
   *   answers with what it drew of them, each taken as the canvas takes any diagram's.
   */
  constructor(
    base: Saved,
    saving: Saving,
    read: () => Scene,
    said: (said: Said) => void,
    moved: (
      elements: Record<string, ElementJson>,
      files: Readonly<Record<string, FileJson>>,
    ) => Record<string, ElementJson>,
    clock: Clock = WINDOW,
  ) {
    this.#base = base;
    this.#saving = saving;
    this.#read = read;
    this.#said = said;
    this.#moved = moved;
    this.#clock = clock;
  }

  /** The version last saved on. */
  get version(): number {
    return this.#base.version;
  }

  /** The canvas changed: save after two seconds of quiet. Until it is saved, it says so. */
  changed(): void {
    this.#dirty = true;
    if (!this.#stopped && !this.#closing) this.#saying({ state: "saving" });
    this.#schedule(QUIET);
  }

  /** The person let go of what they drew: save as soon as the cadence allows. */
  released(): void {
    if (this.#dirty) this.#schedule(0);
  }

  /**
   * The canvas is closing: what it holds that isn't saved is sent now, whatever the cadence, and
   * nothing after it.
   */
  close(): void {
    this.#closing = true;
    this.#cancel?.();
    if (this.#dirty) void this.flush();
  }

  /**
   * A newer revision was drawn, someone else's, as Excalidraw reconciles it: what is saved next
   * is an edit of it. An edit kept here after moving too often goes now.
   */
  merged(head: Saved, drawn: Readonly<Record<string, ElementJson>>): void {
    // While a save is in flight, its answer says what follows: applied, the version moves on; a
    // conflict, the head is read again. Either way this revision is in what comes next.
    if (this.#stopped || this.#inFlight || head.version <= this.#base.version) return;
    this.#base = onto(head, drawn);
    if (this.#parked) {
      this.#parked = false;
      this.#schedule(0);
    }
  }

  /** Stop saving, and say nothing more. */
  stop(): void {
    this.#stopped = true;
    this.#cancel?.();
  }

  #schedule(wait: number): void {
    if (this.#stopped || this.#closing) return;
    this.#cancel?.();
    const at = Math.max(this.#clock.now() + wait, this.#sentAt + EVERY);
    this.#cancel = this.#clock.after(at - this.#clock.now(), () => void this.flush());
  }

  /** Save what has changed since the version last saved on, now: one save at a time. */
  async flush(moves = MOVES): Promise<void> {
    if (this.#stopped || this.#inFlight) return;
    this.#cancel = null;
    const now = this.#drawn ?? this.#read();
    this.#drawn = null;
    if (Object.keys(now.elements).length > MAX_ELEMENTS || bytes(now) > MAX_BYTES) {
      this.#stop(`A diagram holds at most ${MAX_ELEMENTS} elements and 1 MiB: this isn't saved.`);
      return;
    }
    const ops = elementPatch(this.#base.scene, now.elements, now.files);
    this.#dirty = false;
    if (ops.length === 0) {
      this.#saying({ state: "saved" });
      return;
    }
    this.#inFlight = true;
    this.#sentAt = this.#clock.now();
    this.#saying({ state: "saving" });
    const base = this.#base;
    let done: Committed;
    try {
      done = await this.#saving.commit({ baseVersion: base.version, ops, summary: summary(ops) });
    } catch {
      done = { outcome: "refused", said: "The connection to the workspace closed." };
    }
    this.#inFlight = false;
    switch (done.outcome) {
      case "applied":
        this.#base = {
          version: done.version,
          scene: {
            elements: { ...base.scene.elements, ...now.elements },
            files: { ...base.scene.files, ...now.files },
          },
        };
        if (!this.#dirty) this.#saying({ state: "saved" });
        break;
      case "proposed":
        this.#stop("Your changes were proposed, for someone to accept: the canvas stops saving.");
        return;
      case "refused":
        this.#stop(`Not saved. ${done.said}`);
        return;
      case "conflict": {
        const head = await this.#saving.head().catch(() => null);
        if (head === null) {
          this.#stop("Not saved. It couldn't be read again: close it, and open it again.");
          return;
        }
        if (moves <= 0) {
          // Moved too often: the edit stays here, unsaved, and goes with the next revision.
          this.#dirty = true;
          this.#parked = true;
          return;
        }
        // Drawn as the canvas takes any diagram: what the head holds that it never draws, such
        // as a link or an embedded page, never reaches the scene.
        // The head's images, a peer's or an agent's, with this person's: what may be drawn.
        const files = { ...head.scene.files, ...now.files };
        const drawn = this.#moved(rebase(base.scene, now.elements, head.scene), files);
        this.#base = onto(head, drawn);
        // The next save sends what was drawn, even as the canvas closes and can't be read again.
        this.#drawn = { elements: drawn, files };
        await this.flush(moves - 1);
        return;
      }
    }
    if (this.#dirty && this.#closing) await this.flush();
    else if (this.#dirty) this.#schedule(QUIET);
  }

  #stop(text: string): void {
    this.stop();
    this.#saying({ state: "stopped", text });
  }

  /** Say what the canvas says of its saving, once for each time it changes. */
  #saying(said: NonNullable<Said>): void {
    if (said.state !== "stopped" && said.state === this.#saidLast) return;
    this.#saidLast = said.state;
    this.#said(said);
  }
}
