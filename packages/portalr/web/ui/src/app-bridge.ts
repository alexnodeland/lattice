/**
 * The bridge between a mini app and the page it runs in (lattice RFC-0005, portalr ADR-0051):
 * JSON-RPC 2.0 over `postMessage`, on MCP Apps' method names, which the agent's tools describe to
 * the model (artifactr ADR-0082). The app runs in a frame inside the sandbox, on the apps' origin;
 * the sandbox relays what the app sends as JSON text, which the host takes only from the sandbox's
 * window and origin, reads only if it is within the size a message may be, and answers only if it
 * is a request the bridge knows, within the frame's calls a minute. The app reaches three tools,
 * its own state and its submissions, and nothing else; the host acts as the person viewing it.
 */

import { isNumber, isObject, isString } from "./json";
import { safeHref } from "./safe-href";

/** The version of MCP Apps' protocol whose method names the bridge speaks. */
const PROTOCOL = "2026-01-26";

/** The largest message, either way, in the UTF-8 bytes of its JSON. */
export const MOST_MESSAGE = 64 * 1024;

/** The largest state an app keeps, in the UTF-8 bytes of its JSON, as artifactr.ui holds it. */
export const MOST_STATE = 64 * 1024;

/** How many messages a frame may send in a minute, after which the host stops answering it. */
export const CALLS_A_MINUTE = 60;

/** How often a frame's state is written, at most: one version every five seconds. */
export const STATE_EVERY = 5_000;

/** What the sandbox says once it is ready for the app's HTML, and what the host answers with. */
export const PROXY_READY = "ui/notifications/sandbox-proxy-ready";
export const RESOURCE_READY = "ui/notifications/sandbox-resource-ready";

/** What an app says of its height, which the host sizes its frame to. */
const SIZE_CHANGED = "ui/notifications/size-changed";

/** What the host sends the app when its theme, colours or modes change. */
const CONTEXT_CHANGED = "ui/notifications/host-context-changed";

/** portalr's own, said by the app's document before the app's HTML: it runs. */
export const APP_STARTED = "portalr/app-started";

/**
 * portalr's own, said by the app's document of the app: an error, a refused promise or a refusal
 * of its policy, the first five that differ; and once, after it loaded, what it drew.
 */
export const APP_ERROR = "portalr/app-error";
export const APP_BOOT = "portalr/app-boot";

/**
 * portalr's own, said by the app's document after an uncaught error, where the app was drawing
 * frames: `stopped` "yes" where none came in the 2 s after it, "no" where they went on or came back.
 */
export const APP_STOPPED = "portalr/app-stopped";

/** The notifications an app may send; any other is dropped, and any other request refused. */
const NOTIFICATIONS = new Set([
  PROXY_READY,
  APP_STARTED,
  APP_ERROR,
  APP_BOOT,
  APP_STOPPED,
  "ui/notifications/initialized",
  SIZE_CHANGED,
]);

type Json = null | boolean | number | string | readonly Json[] | { readonly [key: string]: Json };
export type JsonObject = { readonly [key: string]: Json };

/** What an app sent that the host reads: a request it answers, or a notification. */
export type Message =
  | {
      readonly kind: "request";
      readonly id: string | number;
      readonly method: string;
      readonly params: JsonObject;
    }
  | { readonly kind: "notification"; readonly method: string; readonly params: JsonObject };

/** The UTF-8 bytes of a value's JSON, as artifactr.ui measures a size. */
const jsonSize = (value: unknown): number => new TextEncoder().encode(JSON.stringify(value)).length;

/**
 * What a frame sent, as the sandbox relayed it: JSON text, within `MOST_MESSAGE`, of a JSON-RPC
 * 2.0 request, or a notification the bridge knows; null for anything else, which is dropped. A
 * request for a method the bridge doesn't know is read, so it can be told so.
 */
export function readMessage(text: unknown): Message | null {
  if (!isString(text) || new TextEncoder().encode(text).length > MOST_MESSAGE) {
    return null;
  }
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return null;
  }
  if (!isObject(data) || data.jsonrpc !== "2.0" || !isString(data.method)) {
    return null;
  }
  const params = data.params === undefined ? {} : data.params;
  if (!isObject(params)) {
    return null;
  }
  const { id, method } = data;
  if (id === undefined) {
    return NOTIFICATIONS.has(method)
      ? { kind: "notification", method, params: params as JsonObject }
      : null;
  }
  if (!(isString(id) || isNumber(id))) {
    return null;
  }
  return { kind: "request", id, method, params: params as JsonObject };
}

/** The least time between two of the sandbox's measures the host hears, in milliseconds. */
const MEASURED_EVERY = 200;

/** A size the sandbox measured for the app, as `appDocument`'s script says it. */
const isMeasured = (message: NonNullable<ReturnType<typeof readMessage>>) =>
  message.kind === "notification" &&
  message.method === SIZE_CHANGED &&
  message.params.measured === true &&
  isNumber(message.params.height);

/** A tool's result, as MCP's `tools/call` answers: its structured content, and the same as text. */
const toolResult = (structured: JsonObject) => ({
  content: [{ type: "text", text: JSON.stringify(structured) }],
  structuredContent: structured,
});

/** A tool's refusal, as MCP's `tools/call` answers one: what it says, and that it is an error. */
const toolRefusal = (said: string) => ({
  content: [{ type: "text", text: said }],
  isError: true,
});

/** At most `limit` takes in any `window` milliseconds, by the clock `now` reads. */
export class Limiter {
  readonly #taken: number[] = [];
  readonly #limit: number;
  readonly #window: number;
  readonly #now: () => number;
  constructor(limit: number, window: number, now: () => number = Date.now) {
    this.#limit = limit;
    this.#window = window;
    this.#now = now;
  }
  /** Take one, if any is left in the window; whether one was. */
  take(): boolean {
    const at = this.#now();
    while (this.#taken.length > 0 && (this.#taken[0] ?? at) <= at - this.#window) {
      this.#taken.shift();
    }
    if (this.#taken.length >= this.#limit) {
      return false;
    }
    this.#taken.push(at);
    return true;
  }
}

// ─── what the app's document reports ─────────────────────────────────────────

/**
 * The most reports a frame's bridge passes on: five errors and three of what it drew; and,
 * counted apart so no earlier report can crowd them out, four of whether it stopped.
 */
export const MOST_REPORTS = 8;
export const MOST_STOPPED = 4;

/** Each report's fields: text kept to so many characters, or a number (`0`). Others are dropped. */
const REPORTED: Readonly<Record<string, Readonly<Record<string, number>>>> = {
  [APP_ERROR]: {
    kind: 20,
    message: 300,
    stack: 400,
    source: 120,
    line: 0,
    directive: 60,
    blocked: 200,
  },
  [APP_STOPPED]: { stopped: 3, message: 300, stack: 400 },
  [APP_BOOT]: {
    drawn: 20,
    readyState: 20,
    children: 0,
    canvases: 0,
    canvasWidth: 0,
    canvasHeight: 0,
    canvasContext: 30,
    canvasPixels: 20,
    width: 0,
    height: 0,
    pixelRatio: 0,
    sandboxWidth: 0,
    sandboxHeight: 0,
    frameWidth: 0,
    frameHeight: 0,
    userAgent: 120,
    has: 120,
  },
};

/** What an error is said to be; any other is an error. */
const KINDS = new Set(["error", "load", "rejection", "policy"]);

/** The most a number reported may be: none is ever more, or less than nothing. */
const MOST_NUMBER = 100_000;

/** What could hide or reorder the text around it, or break its line: controls, formats, breaks. */
const UNSHOWN = /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/gu;

/** Text as one plain line of at most `most` characters, never half of one; the unshown, spaces. */
const oneLine = (text: string, most: number) =>
  Array.from(text).slice(0, most).join("").replace(UNSHOWN, " ");

/** What an app's document reported: untrusted text and numbers, for plain text alone. */
export type Report = {
  readonly method: typeof APP_ERROR | typeof APP_BOOT | typeof APP_STOPPED;
  readonly params: Readonly<Record<string, string | number>>;
};

/** A report's fields the bridge knows, text cut short and stripped; null if none is left. */
export function readReport(method: string, params: JsonObject): Report | null {
  const fields = REPORTED[method];
  if (fields === undefined) {
    return null;
  }
  const kept: Record<string, string | number> = {};
  for (const [name, most] of Object.entries(fields)) {
    const value = params[name];
    if (most > 0 && isString(value)) {
      kept[name] = oneLine(value, most);
    } else if (most === 0 && isNumber(value) && Number.isFinite(value)) {
      kept[name] = Math.min(MOST_NUMBER, Math.max(0, value));
    }
  }
  if (Object.keys(kept).length === 0) {
    return null;
  }
  if (method === APP_ERROR && !KINDS.has(String(kept.kind))) {
    kept.kind = "error";
  }
  return { method: method as Report["method"], params: kept };
}

// ─── JSON Patch ───────────────────────────────────────────────────────────────

/** A JSON Patch that can't be applied: an operation the RFC lacks, a missing path, a failed test. */
export class PatchRefused extends Error {}

type Container = Json[] | { [key: string]: Json };

/** The keys of a JSON Pointer, unescaped: `/a~1b/0` is `["a/b", "0"]`. */
function keysOf(pointer: unknown): string[] {
  if (!isString(pointer) || (pointer !== "" && !pointer.startsWith("/"))) {
    throw new PatchRefused(`${String(pointer)} is no JSON Pointer`);
  }
  return pointer === ""
    ? []
    : pointer
        .slice(1)
        .split("/")
        .map((key) => key.replaceAll("~1", "/").replaceAll("~0", "~"));
}

const copy = (value: Json): Json => structuredClone(value);

function parentOf(document: Json, keys: readonly string[]): [Container, string] {
  let at: Json = document;
  for (const key of keys.slice(0, -1)) {
    at = childOf(at, key);
  }
  if (at === null || typeof at !== "object") {
    throw new PatchRefused(`/${keys.join("/")} has no parent to hold it`);
  }
  return [at as Container, keys.at(-1) ?? ""];
}

function childOf(at: Json, key: string): Json {
  if (Array.isArray(at)) {
    const index = indexOf(at, key, false);
    return at[index] as Json;
  }
  if (at !== null && typeof at === "object" && Object.hasOwn(at, key)) {
    return (at as { [key: string]: Json })[key] as Json;
  }
  throw new PatchRefused(`there is nothing at ${key}`);
}

function indexOf(list: readonly Json[], key: string, adding: boolean): number {
  if (adding && key === "-") {
    return list.length;
  }
  const index = /^(0|[1-9]\d*)$/.test(key) ? Number(key) : Number.NaN;
  if (!(index < list.length + (adding ? 1 : 0))) {
    throw new PatchRefused(`${key} is no index of a list of ${list.length}`);
  }
  return index;
}

function read(document: Json, keys: readonly string[]): Json {
  return keys.reduce<Json>((at, key) => childOf(at, key), document);
}

function remove(document: Json, keys: readonly string[]): Json {
  const [parent, key] = parentOf(document, keys);
  const was = childOf(parent, key);
  if (Array.isArray(parent)) {
    parent.splice(indexOf(parent, key, false), 1);
  } else {
    delete parent[key];
  }
  return was;
}

function add(document: Json, keys: readonly string[], value: Json): Json {
  if (keys.length === 0) {
    return value;
  }
  const [parent, key] = parentOf(document, keys);
  if (Array.isArray(parent)) {
    parent.splice(indexOf(parent, key, true), 0, value);
  } else {
    parent[key] = value;
  }
  return document;
}

/**
 * An app's state with a JSON Patch applied (RFC 6902): `add`, `remove`, `replace`, `move`, `copy`
 * and `test`, all or nothing. The state stays an object; anything else is refused.
 */
export function applyPatch(state: JsonObject, patch: unknown): JsonObject {
  if (!Array.isArray(patch)) {
    throw new PatchRefused("a patch is a list of operations");
  }
  let document: Json = copy(state);
  for (const op of patch as unknown[]) {
    if (!isObject(op)) {
      throw new PatchRefused("each operation is an object");
    }
    const keys = keysOf(op.path);
    const value = op.value as Json;
    switch (op.op) {
      case "add":
        document = add(document, keys, copy(value));
        break;
      case "remove":
        if (keys.length === 0) {
          throw new PatchRefused("the state itself is never removed");
        }
        remove(document, keys);
        break;
      case "replace":
        if (keys.length === 0) {
          document = copy(value);
        } else {
          remove(document, keys);
          document = add(document, keys, copy(value));
        }
        break;
      case "move": {
        const from = keysOf(op.from);
        document = add(document, keys, remove(document, from));
        break;
      }
      case "copy":
        document = add(document, keys, copy(read(document, keysOf(op.from))));
        break;
      case "test":
        if (JSON.stringify(read(document, keys)) !== JSON.stringify(value)) {
          throw new PatchRefused(`${String(op.path)} is not what the test says`);
        }
        break;
      default:
        throw new PatchRefused(`${String(op.op)} is no operation of JSON Patch`);
    }
  }
  if (document === null || typeof document !== "object" || Array.isArray(document)) {
    throw new PatchRefused("an app's state is an object");
  }
  return document as JsonObject;
}

// ─── the state, coalesced ─────────────────────────────────────────────────────

/** How a write of the state ended: done; refused for a version since, to write again; or not. */
export type Written = "done" | "stale" | { readonly refused: unknown };

/**
 * An app's state as its frame sees it: the head's, with the patches it set since applied, written
 * as one version at most every `STATE_EVERY`. A write made against a head that moved on is made
 * again on the new head, the patches applied to it; one refused for another reason is dropped,
 * and the state is the head's again.
 */
export class StateKeeper {
  #head: { state: JsonObject; version: number };
  #pending: unknown[] = [];
  #local: JsonObject;
  #last = Number.NEGATIVE_INFINITY;
  #timer: ReturnType<typeof setTimeout> | null = null;
  #writing = false;
  // A write found the head moved on: the next waits for the new head.
  #stale = false;
  readonly #write: (state: JsonObject, version: number) => Promise<Written>;
  readonly #refused: (rejection: unknown) => void;
  readonly #now: () => number;

  constructor(
    head: { state: JsonObject; version: number },
    write: (state: JsonObject, version: number) => Promise<Written>,
    refused: (rejection: unknown) => void,
    now: () => number = Date.now,
  ) {
    this.#head = head;
    this.#local = head.state;
    this.#write = write;
    this.#refused = refused;
    this.#now = now;
  }

  /** The state the app sees, and the version it is on. */
  get current(): { state: JsonObject; version: number } {
    return { state: this.#local, version: this.#head.version };
  }

  /** Apply a patch the app set, within `MOST_STATE`, and write it in time; the state it makes. */
  set(patch: unknown): JsonObject {
    const next = applyPatch(this.#local, patch);
    if (jsonSize(next) > MOST_STATE) {
      throw new PatchRefused(`the state would be over ${MOST_STATE} bytes`);
    }
    this.#pending.push(patch);
    this.#local = next;
    this.#schedule();
    return next;
  }

  /** The artifact moved on, to `head`: the patches not yet written, applied to it. */
  rebase(head: { state: JsonObject; version: number }): void {
    if (head.version <= this.#head.version) {
      return;
    }
    this.#head = head;
    this.#stale = false;
    try {
      this.#local = this.#pending.reduce<JsonObject>(
        (state, patch) => applyPatch(state, patch),
        head.state,
      );
    } catch {
      this.#pending = [];
      this.#local = head.state;
    }
    this.#schedule();
  }

  /** Stop writing: the frame is gone. */
  stop(): void {
    if (this.#timer !== null) {
      clearTimeout(this.#timer);
      this.#timer = null;
    }
  }

  #schedule(): void {
    if (this.#timer !== null || this.#writing || this.#stale || this.#pending.length === 0) {
      return;
    }
    const wait = Math.max(0, this.#last + STATE_EVERY - this.#now());
    this.#timer = setTimeout(() => void this.#flush(), wait);
  }

  async #flush(): Promise<void> {
    this.#timer = null;
    const written = this.#pending.length;
    const sent = this.#local;
    const { version } = this.#head;
    this.#writing = true;
    this.#last = this.#now();
    const ended = await this.#write(sent, version);
    this.#writing = false;
    if (ended === "done") {
      this.#pending = this.#pending.slice(written);
      // What was written is the next version: the artifact's own arrives as a rebase onto it.
      this.#head = { state: sent, version: version + 1 };
    } else if (ended === "stale") {
      this.#stale = true;
    } else {
      this.#pending = [];
      this.#local = this.#head.state;
      this.#refused(ended.refused);
    }
    this.#schedule();
  }
}

// ─── the bridge ───────────────────────────────────────────────────────────────

/** The height a frame may be sized to, in pixels: an app's ask is kept within it. */
const LEAST_HEIGHT = 120;
export const MOST_HEIGHT = 2_000;

/** What the person is asked, outside the frame, before the host acts for the app. */
export type Question =
  | { readonly kind: "submit"; readonly values: JsonObject }
  | { readonly kind: "link"; readonly url: string };

/** What a bridge does for its frame, as the page running it, for the person viewing it. */
export interface BridgeHost {
  /** The app's title and HTML, sent to its sandbox once it is ready. */
  readonly app: () => { readonly title: string; readonly html: string };
  /** The host's context: its theme, colours and modes. */
  readonly context: () => JsonObject;
  /** Ask the person, outside the frame; whether they said yes. */
  readonly ask: (question: Question) => Promise<boolean>;
  /** Send values as the person's submission to the app: its id, or null where it wasn't sent. */
  readonly submit: (values: JsonObject) => Promise<string | null>;
  /**
   * Why nothing is submitted from here at all, as from a preview of an old version: said to the
   * app at once, before the person is asked anything; or nothing, where submissions are sent.
   */
  readonly submitsNothing?: () => string | undefined;
  /** Open a link the person agreed to, in a new tab. */
  readonly open: (url: string) => void;
  /** Size the frame to a height, in pixels, within `LEAST_HEIGHT` and `MOST_HEIGHT`. */
  readonly resize: (height: number) => void;
  /** The frame sent past its calls a minute, and isn't answered for now. */
  readonly quieted: () => void;
  /** The sandbox said it is ready: its page runs. */
  readonly ready: () => void;
  /** The app's document said something: it runs, whether or not it uses the bridge. */
  readonly started: () => void;
  /** The app's document reported an error, or what it drew: untrusted, for plain text alone. */
  readonly reported?: (report: Report) => void;
}

/**
 * One frame's bridge: what it hears from its sandbox, from `source` at `origin` alone, and the
 * answers it posts back through `post`, as the person viewing the app. Its state is `state`'s.
 */
export class Bridge {
  readonly #source: unknown;
  readonly #origin: string;
  readonly #post: (message: JsonObject) => void;
  readonly #host: BridgeHost;
  readonly #state: StateKeeper;
  readonly #limiter: Limiter;
  /** Whether the app has said its own height, which the sandbox's measure then gives way to. */
  #sized = false;
  /** When the sandbox's measure was last applied, by `#now`. */
  #measuredAt = Number.NEGATIVE_INFINITY;
  /** The latest measure heard too soon after the last, applied when its time comes. */
  #held: { height: number; timer: ReturnType<typeof setTimeout> } | null = null;
  /** How many of the app's reports were passed on, up to `MOST_REPORTS`, and of whether it stopped. */
  #reports = 0;
  #stopped = 0;
  readonly #now: () => number;

  constructor(options: {
    source: unknown;
    origin: string;
    post: (message: JsonObject) => void;
    host: BridgeHost;
    state: StateKeeper;
    now?: () => number;
  }) {
    this.#source = options.source;
    this.#origin = options.origin;
    this.#post = options.post;
    this.#host = options.host;
    this.#state = options.state;
    this.#limiter = new Limiter(CALLS_A_MINUTE, 60_000, options.now);
    this.#now = options.now ?? Date.now;
  }

  /**
   * A height the app said, or the sandbox measured for it (`measured`, portalr's own). The app's
   * own wins from the first it says; one below `LEAST_HEIGHT`, as a height measured before the
   * app was laid out is, is no height, and leaves the measure to size it.
   */
  #sizeChanged(height: number, measured: boolean) {
    if (!measured) {
      if (height < LEAST_HEIGHT) {
        return;
      }
      this.#sized = true;
    } else if (this.#sized) {
      return;
    }
    this.#host.resize(Math.round(Math.min(MOST_HEIGHT, height)));
  }

  /**
   * The sandbox's own measure, not the app's: never counted against it, and applied at most
   * every `MEASURED_EVERY`. One heard sooner is held, the latest replacing the one before, and
   * applied when its time comes, since the sandbox says a height once, when it changes: a final
   * height bunched behind another is never lost.
   */
  #measure(height: number) {
    const wait = this.#measuredAt + MEASURED_EVERY - this.#now();
    if (wait > 0) {
      if (this.#held === null) {
        const timer = setTimeout(() => {
          const held = this.#held;
          this.#held = null;
          if (held !== null) {
            this.#measure(held.height);
          }
        }, wait);
        this.#held = { height, timer };
      } else {
        this.#held = { ...this.#held, height };
      }
      return;
    }
    this.#measuredAt = this.#now();
    this.#sizeChanged(height, true);
  }

  /**
   * Give the sandbox the app: when it says it is ready, and when its frame loads, by which time a
   * sandbox listens, so a ready the host didn't hear, or a post to a page that wasn't yet the
   * sandbox's, isn't the end of it. The sandbox runs the first it is given and drops the rest.
   */
  give(): void {
    this.#notify(RESOURCE_READY, { ...this.#host.app() });
  }

  /** Hear a message: answered if it is the sandbox's, within its calls a minute; else dropped. */
  heard(event: { readonly source: unknown; readonly origin: string; readonly data: unknown }) {
    if (event.source !== this.#source || event.origin !== this.#origin) {
      return; // not this app's sandbox: dropped, whatever it says
    }
    // Only what could be the sandbox's measure is read before the limit: the rest is counted
    // first, so an app past its limit has none of its messages read.
    const measured = isString(event.data) && event.data.includes('"measured"');
    const read = measured ? readMessage(event.data) : null;
    if (read !== null && isMeasured(read)) {
      this.#host.started();
      this.#measure(read.params.height as number);
      return;
    }
    if (!this.#limiter.take()) {
      this.#host.quieted();
      return;
    }
    const message = read ?? readMessage(event.data);
    if (message === null) {
      return;
    }
    const { method, params } = message;
    if (method === PROXY_READY) {
      this.#host.ready();
      return this.give();
    }
    this.#host.started(); // anything else is the app's document's, so it runs
    if (message.kind === "notification") {
      if (method === SIZE_CHANGED && isNumber(params.height)) {
        this.#sizeChanged(params.height, params.measured === true);
      }
      const stopped = method === APP_STOPPED;
      const room = stopped ? this.#stopped < MOST_STOPPED : this.#reports < MOST_REPORTS;
      const report = room ? readReport(method, params) : null;
      if (report !== null) {
        if (stopped) {
          this.#stopped += 1;
        } else {
          this.#reports += 1;
        }
        this.#host.reported?.(report);
      }
      return;
    }
    const { id } = message;
    switch (method) {
      case "ui/initialize":
        return this.#answer(id, {
          protocolVersion: PROTOCOL,
          hostInfo: { name: "portalr" },
          hostCapabilities: { openLinks: {}, serverTools: {} },
          hostContext: this.#host.context(),
        });
      case "tools/call":
        return void this.#call(id, params);
      case "ui/open-link":
        return void this.#link(id, params);
      default:
        return this.#fail(id, -32601, `${method} is no method of the host's`);
    }
  }

  /** Send the host's context again, as its theme, colours or modes changed. */
  contextChanged(): void {
    this.#notify(CONTEXT_CHANGED, this.#host.context());
  }

  #notify(method: string, params: JsonObject) {
    this.#post({ jsonrpc: "2.0", method, params });
  }

  #answer(id: string | number, result: JsonObject) {
    this.#post({ jsonrpc: "2.0", id, result });
  }

  #fail(id: string | number, code: number, message: string) {
    this.#post({ jsonrpc: "2.0", id, error: { code, message } });
  }

  async #call(id: string | number, params: JsonObject) {
    const args = isObject(params.arguments) ? params.arguments : {};
    switch (params.name) {
      case "get_state":
        return this.#answer(id, toolResult(this.#state.current));
      case "set_state":
        try {
          return this.#answer(id, toolResult({ state: this.#state.set(args.patch) }));
        } catch (error) {
          // A patch's own refusal, which names only what the app sent; anything else, no words.
          return this.#answer(
            id,
            toolRefusal(error instanceof PatchRefused ? error.message : "refused"),
          );
        }
      case "submit": {
        const { values } = args;
        if (!isObject(values)) {
          return this.#answer(id, toolRefusal("submit takes `values`, an object"));
        }
        const nothing = this.#host.submitsNothing?.();
        if (nothing !== undefined) {
          return this.#answer(id, toolRefusal(nothing));
        }
        if (!(await this.#host.ask({ kind: "submit", values: values as JsonObject }))) {
          return this.#answer(id, toolRefusal("The person didn't send it."));
        }
        const sent = await this.#host.submit(values as JsonObject);
        return this.#answer(
          id,
          sent === null
            ? toolRefusal("It wasn't sent: the server refused it, or the connection closed.")
            : toolResult({ submitted: true, id: sent }),
        );
      }
      default:
        return this.#answer(id, toolRefusal(`${String(params.name)} is no tool of this app's`));
    }
  }

  async #link(id: string | number, params: JsonObject) {
    const url = isString(params.url) ? params.url : "";
    const opened = safeHref(url) ?? (/^mailto:[^/]/i.test(url) ? url : null);
    if (opened === null) {
      return this.#fail(id, -32602, "Only an http, https or mailto link opens.");
    }
    if (!(await this.#host.ask({ kind: "link", url: opened }))) {
      return this.#fail(id, -32000, "The person didn't open it.");
    }
    this.#host.open(opened);
    return this.#answer(id, {});
  }
}
