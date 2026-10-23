// What the worker's server decides without a browser: which file a request for the page names,
// which images a render may hold, and one warm thing, made at most once at a time.

import { normalize } from "node:path";

/**
 * The file of the page's a request's path names, inside the page's directory, or undefined for
 * a path that isn't one: one that doesn't decode, or holds a NUL.
 */
export function servedPath(pathname: string): string | undefined {
  let decoded: string;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return undefined;
  }
  if (decoded.includes("\0")) return undefined;
  // Normalised from the root, `..` can't climb above it.
  return normalize(`/${decoded}`).replace(/^\/+/, "");
}

/** The images a render may hold: a PNG or a JPEG, as artifactr's checks of an SVG allow. */
export const IMAGE_TYPES: ReadonlySet<string> = new Set(["image/png", "image/jpeg"]);

/** Base64, and nothing else. */
const BASE64 = /^[A-Za-z0-9+/]*={0,2}$/;

/**
 * Why a render's images can't be drawn, or undefined if they can: each is base64, of a type the
 * diagram names and a render may hold.
 */
export function imagesRefused(
  files: Record<string, unknown>,
  named: Record<string, { media_type?: unknown } | undefined>,
): string | undefined {
  for (const [id, data] of Object.entries(files)) {
    if (typeof data !== "string" || !BASE64.test(data)) return `image ${id} isn't base64`;
    const type = named[id]?.media_type;
    if (typeof type !== "string" || !IMAGE_TYPES.has(type)) {
      return `image ${id} is ${String(type)}: a render holds PNGs and JPEGs`;
    }
  }
  return undefined;
}

/**
 * One warm thing, such as the browser's page: made when first asked for, and at most once at a
 * time, so a job that gives up waiting for it leaves no second one being made behind it.
 */
export class Warm<T> {
  private held: T | undefined;
  private making: Promise<T> | undefined;

  private readonly make: () => Promise<T>;
  private readonly alive: (held: T) => boolean;
  private readonly close: (held: T) => Promise<void>;

  constructor(
    make: () => Promise<T>,
    alive: (held: T) => boolean,
    close: (held: T) => Promise<void>,
  ) {
    this.make = make;
    this.alive = alive;
    this.close = close;
  }

  /** The warm thing, made if there is none, or the one being made. */
  get(): Promise<T> {
    if (this.held !== undefined && this.alive(this.held)) return Promise.resolve(this.held);
    this.making ??= this.make()
      .then((made) => {
        this.held = made;
        return made;
      })
      .finally(() => {
        this.making = undefined;
      });
    return this.making;
  }

  /** Throw it away, once any being made is made, so the next `get` makes it anew. */
  async discard(): Promise<void> {
    await this.making?.catch(() => undefined);
    const held = this.held;
    this.held = undefined;
    if (held !== undefined) await this.close(held).catch(() => undefined);
  }

  /** Make the next one now, so the next job doesn't wait for it, if it doesn't come soon. */
  warm(): void {
    this.get().catch((error: unknown) => console.error(`couldn't warm the page: ${error}`));
  }
}
