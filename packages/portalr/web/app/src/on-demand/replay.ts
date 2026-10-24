/**
 * Session replay's recorder (lattice RFC-0008, portalr ADR-0077), loaded once a person has said
 * yes to replay as well as to analytics: someone who never does never loads rrweb.
 *
 * It records the layout of the pages in a tenant and where the person clicks, and nothing they
 * wrote: every text and every input value is masked as rrweb records it, mini apps' frames and
 * the regions a page marks are blocked outright, and the attributes that carry words or an
 * address are masked again before a batch leaves the browser. The relay checks each batch once
 * more, and drops one that holds a word. A batch goes to portalr's relay alone, in the session it
 * signed; one that fails is dropped, never retried, so replay never slows or fails a screen.
 */

import type { Api } from "@portalr/client";
import { record } from "rrweb";
import {
  attributes,
  css_text,
  doctype,
  keys,
  limits,
  marks,
  name,
  namespaces,
  patterns,
  script,
  structural_keys,
  style,
  styled,
  worded,
} from "../../../../src/portalr/analytics/replay_allowlist.json";

/**
 * What may be unmasked, which the relay reads too (portalr's `analytics/replay_allowlist.json`).
 * An attribute is kept only by name and pattern, and anything else that isn't asterisks is masked
 * or, if its name is not one the list knows, left out. The relay checks what is sent against the
 * same file, so a pattern wrong here is wrong there. No stylesheet text is sent: a page's own
 * stylesheet is named by its file, and the relay puts in the file's text; other CSS is left out.
 * Every string is capped in length before any pattern is tried, and each pattern is linear.
 */
const full = (text: string) => new RegExp(`^(?:${text})$`);
const PATTERNS = new Map(Object.entries(patterns).map(([key, text]) => [key, full(text)]));
const ATTRIBUTES = new Map(Object.entries(attributes));
const NAMESPACES = new Map(Object.entries(namespaces));
const WORDED: ReadonlySet<string> = new Set(worded);
const STYLED: ReadonlySet<string> = new Set(styled);
const CSS_TEXT: ReadonlySet<string> = new Set(css_text.keys);
const KEYS: ReadonlySet<string> = new Set(keys);
const MARKS = new Map(Object.entries(marks));
const NAME = full(name);
const DOCTYPE = new Map(Object.entries(doctype).map(([key, text]) => [key, full(text)]));
const STRUCTURAL = new Map(Object.entries(structural_keys).map(([key, text]) => [key, full(text)]));
const LIMITS = new Map(Object.entries(limits));
const PROPERTIES: ReadonlySet<string> = new Set(style.properties);
const KEYWORDS: ReadonlySet<string> = new Set(style.keywords);
const OPERATORS: ReadonlySet<string> = new Set([...style.operators]);
const CUSTOM = full(style.custom);
const NUMBER = PATTERNS.get("number") as RegExp;
const NOTHING = css_text.allowed.find((each) => each !== "") ?? "x{}";
const isAscii = (text: string) => {
  for (let at = 0; at < text.length; at += 1) {
    if (text.charCodeAt(at) > 127) {
      return false;
    }
  }
  return true;
};

/** Every pattern this module matches with, for a test that holds each to linear time. */
export const REGEXES: readonly RegExp[] = [
  ...PATTERNS.values(),
  ...DOCTYPE.values(),
  ...STRUCTURAL.values(),
  NAME,
  CUSTOM,
];

/** The most events in one batch: the relay's limit. */
export const MOST_EVENTS = 200;

/** The most events that wait before a batch is sent at once. */
export const BATCH = 50;

/** The most bytes in one batch's events, under the relay's 512 KiB; a larger one is dropped. */
export const MOST_BYTES = 500_000;

/** How long an event waits, in milliseconds, before what has gathered is sent. */
export const WAIT = 5_000;

/** A text with every character that isn't a space masked: its shape is kept, its words aren't. */
const masked = (text: string) => text.replace(/\S/g, "*");
const isMasked = (text: string) => /^[\s*]*$/.test(text);

/** Whether a string is within the list's length for `key`, checked before any pattern. */
const short = (key: string, value: string) => value.length <= (LIMITS.get(key) ?? 256);

/** Whether a word of an inline style's value is a number, a keyword or an operator. */
const tokenOk = (token: string) =>
  KEYWORDS.has(token) || OPERATORS.has(token) || NUMBER.test(token);

/**
 * Whether an inline style is a short list of declarations that can render no word: each has a
 * property from the list (or a custom property's name) and a value of numbers with units and
 * keywords from the list. No string, `url()`, `var()`, escape or comment gets through.
 */
export function declarationsOk(text: string): boolean {
  // Plain ASCII: a Kelvin sign folds to a k in lower case, and `blocK` is then `block`.
  if (!short("style", text) || !isAscii(text)) {
    return false;
  }
  return text.split(";").every((declaration) => {
    if (declaration.trim() === "") {
      return true;
    }
    const colon = declaration.indexOf(":");
    const prop = colon < 0 ? "" : declaration.slice(0, colon).trim().toLowerCase();
    if (colon < 0 || !(PROPERTIES.has(prop) || CUSTOM.test(prop))) {
      return false;
    }
    return declaration
      .slice(colon + 1)
      .replace(/[(),]/g, " ")
      .split(/\s+/)
      .filter(Boolean)
      .every((word) => tokenOk(word.toLowerCase()));
  });
}

/** The changes to an element's inline style, rrweb's diff of it, with any that render text masked. */
function styleChanges(value: object): Record<string, unknown> {
  const kept = (prop: string, shown: unknown) =>
    typeof shown === "string" && short("style", shown) && declarationsOk(`${prop}:${shown}`);
  return Object.fromEntries(
    Object.entries(value).map(([prop, change]) => {
      if (change === null || change === false) {
        return [prop, change];
      }
      if (Array.isArray(change)) {
        const important = change.length === 2 && (change[1] === "" || change[1] === "important");
        return [prop, important && kept(prop, change[0]) ? change : null];
      }
      return [prop, kept(prop, change) ? change : masked(String(change))];
    }),
  );
}

/** Whether an attribute's name is on the list, or a `data-*` or `aria-*` name. */
const named = (attr: string) =>
  ATTRIBUTES.has(attr) ||
  WORDED.has(attr) ||
  MARKS.has(attr) ||
  NAMESPACES.has(attr) ||
  STYLED.has(attr) ||
  attr.startsWith("data-") ||
  attr.startsWith("aria-");

/**
 * An attribute's value, as it may be sent: itself if it is known to be structural, else masked;
 * undefined where its name is not one the list knows, and the attribute goes.
 */
function attribute(attr: string, value: unknown): unknown {
  if (!(NAME.test(attr) && named(attr))) {
    return undefined;
  }
  const allowed = MARKS.get(attr);
  if (allowed) {
    return typeof value === "string" && allowed.includes(value) ? value : (allowed[0] ?? "");
  }
  const kinds = ATTRIBUTES.get(attr);
  if (value !== null && typeof value === "object") {
    return STYLED.has(attr) && !Array.isArray(value) ? styleChanges(value) : null;
  }
  if (typeof value !== "string") {
    return value === null || kinds !== undefined ? value : undefined;
  }
  if (isMasked(value)) {
    return value;
  }
  if (!short(attr, value)) {
    return masked(value);
  }
  if (STYLED.has(attr)) {
    return declarationsOk(value) ? value : masked(value);
  }
  const spaces = NAMESPACES.get(attr);
  if (spaces) {
    return spaces.includes(value) ? value : masked(value);
  }
  const kept = kinds?.split("|").some((kind) => PATTERNS.get(kind)?.test(value));
  return kept ? value : masked(value);
}

/**
 * The name of a page's own stylesheet, from the address of the `<link>` rrweb inlined, if it is
 * one of this origin's CSS files; else none. The relay puts in the text of the file it serves
 * under this name, so no stylesheet text leaves the browser.
 */
function sheetOf(href: unknown): string | null {
  if (typeof href !== "string" || href.length > 512) {
    return null;
  }
  try {
    const url = new URL(href, location.href);
    const at = url.pathname.lastIndexOf("/");
    const file = url.pathname.slice(at + 1);
    // Only the app's own built files: a stylesheet from elsewhere is left out, not named.
    const built = url.pathname.slice(0, at).endsWith("/assets");
    return url.origin === location.origin && built && PATTERNS.get("cssfile")?.test(file)
      ? file
      : null;
  } catch {
    return null;
  }
}

/** Whether a node is rrweb's document type, and its three strings are plain. */
const isDoctype = (node: Record<string, unknown>) =>
  node.type === 1 &&
  "publicId" in node &&
  "systemId" in node &&
  [...DOCTYPE].every(
    ([key, pattern]) =>
      !(key in node) ||
      (typeof node[key] === "string" && short(key, node[key]) && pattern.test(node[key])),
  );

/** A string under `key` of a node that is not an attribute, as it may be sent. */
function text(node: Record<string, unknown>, key: string, value: string): string {
  if (key === "href") {
    // The page's address, in a meta event: a fixed width, so its length says nothing either.
    return "********";
  }
  if (CSS_TEXT.has(key)) {
    // CSS a page makes is not sent, nor its length, but its place is: a rule that does nothing.
    return NOTHING;
  }
  if (isMasked(value)) {
    return value;
  }
  let kept = false;
  if (!short(key, value)) {
    kept = false;
  } else if (key === "textContent") {
    kept = value === script;
  } else if (key === "value" && typeof node.property === "string") {
    // A change to a style declaration: its property, and the value it is given.
    kept = declarationsOk(`${node.property}:${value}`);
  } else if (key === "property") {
    kept =
      isAscii(value) && (PROPERTIES.has(value.toLowerCase()) || CUSTOM.test(value.toLowerCase()));
  } else if (DOCTYPE.has(key) && node.type === 1) {
    kept = isDoctype(node);
  } else if (STRUCTURAL.has(key)) {
    kept = STRUCTURAL.get(key)?.test(value) === true;
  }
  return kept ? value : masked(value);
}

/**
 * The event with every value masked that isn't known to be structural: a key rrweb's events don't
 * have goes, an attribute whose name the list doesn't know goes, strings under keys the allow-list
 * names are kept by pattern, a page's own stylesheet is named, not sent, and every other string
 * is asterisks. The event as recorded isn't changed.
 */
export function scrub<T>(value: T, attributes = false): T {
  if (Array.isArray(value)) {
    return value.map((item) => (typeof item === "string" ? masked(item) : scrub(item))) as T;
  }
  if (value === null || typeof value !== "object") {
    return value;
  }
  const node = value as Record<string, unknown>;
  const copy: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(node)) {
    if (attributes) {
      if (key === "_cssText") {
        // A stylesheet the browser inlined: named by its file if it is the app's, else left out.
        const sheet = sheetOf(node.href);
        if (sheet !== null) {
          copy.rr_css = sheet;
        }
        continue;
      }
      const kept = attribute(key, item);
      if (kept !== undefined) {
        copy[key] = kept;
      }
    } else if (!KEYS.has(key)) {
    } else if (typeof item === "string") {
      copy[key] = key === "textContent" && node.isStyle === true ? "" : text(node, key, item);
    } else if (WORDED.has(key) && item !== null) {
      copy[key] = null;
    } else {
      copy[key] = scrub(item, key === "attributes" && !Array.isArray(item));
    }
  }
  return copy as T;
}

/** The mark of a page that may be recorded. */
const ALLOWED = '[data-portalr-replay="allow"]';

/** The page that marks itself allowed, where `main` is unblocked by it. */
const PAGE = `main > div > ${ALLOWED}`;

/**
 * What is blocked, recorded as an empty box of its size. It fails closed: the page's `main` is
 * blocked unless the page has marked itself `allow`, as a direct child of the content area
 * (`main > div`), so a page that says nothing, a new one, or a not-found page that echoes an
 * address, is not recorded, and a mark deeper in a page's content opens nothing. Besides: what a
 * page marks `block` (a thread, an artifact, and the cells of a list that name things), every
 * frame (mini apps run in one), and every dialog but the nav drawer's, which holds who has access
 * to a thread.
 */
export const BLOCKED = [
  `main:not(:has(> div > ${ALLOWED}))`,
  '[data-portalr-replay="block"]',
  "iframe",
  '[role="dialog"]:not(:has([data-drawer]))',
  '[role="alertdialog"]',
].join(", ");

/** An event, as rrweb records it: loosely, since the relay checks what it holds. */
type ReplayEvent = Record<string, unknown>;

/** What rrweb records with: masks all text and input, and blocks what is marked and frames. */
const RECORDING = {
  maskAllInputs: true,
  maskTextSelector: "*",
  blockSelector: BLOCKED,
  slimDOMOptions: "all",
  recordCanvas: false,
  collectFonts: false,
  // A fixed width, so what a person typed doesn't say how long it was.
  maskInputFn: (value: string) => (value === "" ? "" : "********"),
  inlineImages: false,
  recordCrossOriginIframes: false,
  // Where the person clicks and the page scrolls, not the path the pointer took.
  sampling: { mousemove: false, scroll: 200, input: "last" },
} as const;

/**
 * A person's session in the tenant `tenant`, recorded and sent to the relay in batches, under a
 * session id portalr signs for them when the first goes. Made only after the person says yes.
 */
export class Recorder {
  private readonly waiting: ReplayEvent[] = [];
  private session: Promise<string | null> | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stop: (() => void) | null = null;
  private watching: MutationObserver | null = null;
  private again: ReturnType<typeof setTimeout> | null = null;
  private closed = false;

  private readonly api: Api;
  private readonly tenant: string;
  private readonly wait: number;
  private readonly stopped: () => void;

  /**
   * `wait` is how long a few events wait before they go, `WAIT` unless a test says otherwise.
   * `stopped` is called when the relay says it recorded none of a batch, or won't have the
   * session: the recording stops there, since the person's yes may be gone.
   */
  constructor(api: Api, tenant: string, wait: number = WAIT, stopped: () => void = () => {}) {
    this.api = api;
    this.tenant = tenant;
    this.wait = wait;
    this.stopped = stopped;
  }

  /** Start recording the page, from a full snapshot of it. */
  start(): void {
    if (this.closed || this.stop !== null) {
      return;
    }
    // Without `:has()` the selector that blocks `main` is not valid, and nothing would be blocked.
    if (!CSS.supports("selector(:has(*))")) {
      return;
    }
    this.stop =
      record({
        ...RECORDING,
        emit: (event) => this.add(event as unknown as ReplayEvent),
      }) ?? null;
    // A page that allows itself arrives after the first snapshot, such as one that suspends while
    // it reads: its `main` was blocked then, and what is added under a blocked box is not recorded.
    // So a page marking itself allow is the cue for a new full snapshot.
    let open = document.querySelector(PAGE) !== null;
    this.watching = new MutationObserver(() => {
      const now = document.querySelector(PAGE) !== null;
      if (now && !open && this.again === null) {
        this.again = setTimeout(() => {
          this.again = null;
          if (!this.closed) {
            record.takeFullSnapshot();
          }
        }, 200);
      }
      open = now;
    });
    this.watching.observe(document.documentElement, { childList: true, subtree: true });
  }

  /** Gather an event, masked, sending what has gathered when there are enough, or after a while. */
  add(event: ReplayEvent): void {
    if (this.closed) {
      return;
    }
    this.waiting.push(scrub(event));
    if (this.waiting.length >= BATCH) {
      void this.flush();
    } else if (this.timer === null) {
      this.timer = setTimeout(() => void this.flush(), this.wait);
    }
  }

  /** Stop, as the person says no or leaves the tenant: what waits is dropped, unsent. */
  close(): void {
    this.closed = true;
    this.stop?.();
    this.stop = null;
    this.watching?.disconnect();
    this.watching = null;
    if (this.again !== null) {
      clearTimeout(this.again);
      this.again = null;
    }
    this.waiting.length = 0;
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  /** Stop for good, and say so: the relay recorded nothing, so the person's yes may be gone. */
  private halt(): void {
    if (!this.closed) {
      this.close();
      this.stopped();
    }
  }

  /** Send what has gathered now; a batch the relay doesn't take is dropped. */
  async flush(): Promise<void> {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    const events = this.waiting.splice(0, MOST_EVENTS);
    if (events.length === 0 || this.closed) {
      return;
    }
    if (new TextEncoder().encode(JSON.stringify(events)).length <= MOST_BYTES) {
      // A session the relay no longer takes, as one past its hours, is signed afresh, once.
      for (let tries = 0; tries < 2 && !this.closed; tries += 1) {
        const session = await this.signed();
        if (session === null || this.closed || (await this.send(session, events))) {
          break;
        }
        this.session = null;
        if (tries === 1) {
          this.halt();
        }
      }
    }
    if (this.waiting.length > 0 && !this.closed) {
      void this.flush();
    }
  }

  /** The session portalr signed for this recording, asked for once; null if it couldn't be. */
  private async signed(): Promise<string | null> {
    this.session ??= this.api.portalr
      .POST("/portalr/v1/analytics/session")
      .then(({ data }) => data?.session ?? null)
      .catch(() => null);
    const session = await this.session;
    if (session === null) {
      this.session = null;
    }
    return session;
  }

  /** Send a batch: false only where the relay refused its session, true otherwise. */
  private async send(session: string, events: ReplayEvent[]): Promise<boolean> {
    try {
      const { data, response } = await this.api.portalr.POST("/portalr/v1/analytics/replay", {
        headers: { "X-Tenant": this.tenant },
        body: { session, events },
      });
      if (data?.recorded === 0) {
        this.halt();
      }
      return response.status !== 403;
    } catch {
      return true; // Dropped: replay never fails a screen.
    }
  }
}
