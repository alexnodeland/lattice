/**
 * The sandbox: the page the portal frames on the apps' origin, which runs an agent's app in a
 * frame of its own (lattice RFC-0005, portalr ADR-0051). It is static and holds nothing. Framed by
 * the portal alone (its policy's `frame-ancestors`), it takes the app's HTML from its parent and
 * nothing from anyone else, and runs it in a frame sandboxed to an opaque origin with scripts and
 * nothing more: no forms, popups, top navigation or downloads, and no origin to read. The app's
 * document inherits the sandbox's policy, which loads nothing from anywhere, and begins with the
 * same policy of its own, DNS prefetching off, and WebRTC taken from its window, which no policy
 * refuses in Chromium. A frame the app makes in its own document keeps WebRTC: see `NO_WEBRTC`.
 * What the app sends is relayed to the portal as JSON text, within the size a message may be;
 * what the portal sends is relayed to the app.
 */

import {
  APP_BOOT,
  APP_ERROR,
  APP_STARTED,
  APP_STOPPED,
  MOST_MESSAGE,
  PROXY_READY,
  RESOURCE_READY,
} from "./app-bridge";
import { isObject, isString } from "./json";

/** An app's policy, which the server sends for the sandbox too: `web/ui/csp/app-policy.txt`. */
export const APP_POLICY =
  "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; base-uri 'none'; form-action 'none'";

/**
 * Before the app's own script runs: every WebRTC constructor removed from the app's window, since
 * a peer connection's ICE reaches any address over UDP and no policy refuses it in Chromium. It
 * closes the app's window alone: a `srcdoc` frame the app makes runs a script of its own in a
 * window of its own, which has them, and a peer connection from there is heard (portalr
 * ADR-0051, and the CSP tests' `sandbox.test.ts`).
 */
const NO_WEBRTC =
  "for(const k of Object.getOwnPropertyNames(globalThis))if(/^(webkit|moz)?RTC/.test(k))delete globalThis[k];";

/**
 * The app's size, measured for it, in the app's own document: its height as laid out, whenever
 * it changes, at most every 200 ms, as `ui/notifications/size-changed` with portalr's
 * `measured`. An app that says nothing, or a height taken before it was laid out, is still shown
 * whole, and grows and shrinks with what it draws. A height that grew by just what its window
 * grew (an app at `100vh`, with a margin or a border round it) is the window's, not the app's,
 * and isn't said: the frame stays put rather than climbing. One that says its own height is
 * sized by that instead (the bridge's `#sizeChanged`).
 *
 * The window's growth, worked: an app at `min-height: 100vh` in a body with its 8 px margins
 * measures 376 in a 360 frame, 16 beyond its window, and says it. The frame grows to 376, and it
 * measures 392, again 16 beyond: grown just as its window did, it isn't said, and stays at 376.
 * An app that draws more is beyond its window by more than before, and is said.
 */
const SIZED = [
  'addEventListener("DOMContentLoaded", () => {',
  "  let said = 0, over = null, timer = 0;",
  "  const measure = () => {",
  "    timer = 0;",
  "    const height = Math.ceil(document.documentElement.getBoundingClientRect().height);",
  "    const beyond = height - innerHeight;",
  "    const windowed = height > said && said > 0 && beyond === over;",
  "    over = beyond;",
  "    if (!height || height === said || windowed) return;",
  "    said = height;",
  '    parent.postMessage({ jsonrpc: "2.0", method: "ui/notifications/size-changed", params: { height, measured: true } }, "*");',
  "  };",
  "  new ResizeObserver(() => { timer ||= setTimeout(measure, 200); }).observe(document.documentElement);",
  "  measure();",
  "});",
].join("\n");

/**
 * `window.host`, the bridge's shapes as the app's to use, so an app gets them right by default.
 *
 * - `host.connect()`, once however often it is called, asks `ui/initialize`, says
 *   `initialized`, and keeps the host's theme on the document: its `color-scheme`, `data-theme`,
 *   and its colours as CSS variables, a colour no longer given removed.
 * - `host.call(name, args)` resolves to a tool's `structuredContent`; it rejects with an `Error`
 *   on a refusal (`isError: true` on the error), a JSON-RPC error (its `code`), or no answer in
 *   `ANSWER_WITHIN` ms (`code` `"timeout"`), as past the app's messages a minute. `submit` and
 *   `ui/open-link` have no time limit: they wait for the person, whose answer, either way, the
 *   host gives.
 * - `host.request(method, params)` asks anything else, as `call` does; `host.notify` says.
 * - `host.onAnswer(fn)` runs after every answer, refusal or timeout, a task later, so after the
 *   app's own code that awaited it: a safety net, since the app still renders after its own
 *   changes. `host.onContext(fn)` runs after every theme the host gives, the first, as
 *   `connect()` receives it, included, for colours drawn by script.
 *
 * Its ids are its own (`host:1`), so an app's own requests never meet its answers; it hears its
 * parent, the sandbox, alone. Like the measure, it is the app document's inline script, under
 * the same policy: nothing is loaded.
 */
const ANSWER_WITHIN = 10_000;

const HOST = [
  "(() => {",
  "  let next = 0, connecting = null, applied = [];",
  "  const waiting = new Map(), answered = [], themed = [];",
  '  const post = (message) => parent.postMessage({ jsonrpc: "2.0", ...message }, "*");',
  "  const later = (hooks) => setTimeout(() => {",
  "    for (const hook of hooks) { try { hook(); } catch (error) { console.error(error); } }",
  "  }, 0);",
  "  const failure = (said, more) => Object.assign(new Error(said), more);",
  "  const theme = (context) => {",
  '    if (!context || typeof context !== "object") return;',
  "    const root = document.documentElement;",
  '    if (context.theme === "light" || context.theme === "dark") {',
  "      root.style.colorScheme = context.theme;",
  "      root.dataset.theme = context.theme;",
  "    }",
  "    const colours = context.styles && context.styles.variables;",
  '    if (colours && typeof colours === "object") {',
  '      const names = Object.keys(colours).filter((name) => name.startsWith("--") && typeof colours[name] === "string");',
  "      for (const name of applied) if (!names.includes(name)) root.style.removeProperty(name);",
  "      for (const name of names) root.style.setProperty(name, colours[name]);",
  "      applied = names;",
  "    }",
  "    later(themed);",
  "  };",
  "  const settle = (id, finish) => {",
  "    const pending = waiting.get(id);",
  "    if (!pending) return;",
  "    waiting.delete(id);",
  "    clearTimeout(pending.timer);",
  "    finish(pending);",
  "    later(answered);",
  "  };",
  '  addEventListener("message", (event) => {',
  "    if (event.source !== parent) return;",
  "    const message = event.data;",
  '    if (!message || message.jsonrpc !== "2.0") return;',
  '    if (message.method === "ui/notifications/host-context-changed") theme(message.params);',
  "    if (message.id == null) return;",
  "    settle(message.id, ({ answer, refuse }) => {",
  "      const result = message.result;",
  '      if (message.error) refuse(failure(message.error.message || "refused", { code: message.error.code }));',
  "      else if (result && result.isError) {",
  "        const said = result.content && result.content[0] && result.content[0].text;",
  '        refuse(failure(said || "refused", { isError: true }));',
  "      } else answer(result && result.structuredContent !== undefined ? result.structuredContent : result);",
  "    });",
  "  });",
  "  const request = (method, params = {}) => new Promise((answer, refuse) => {",
  '    const id = "host:" + ++next;',
  '    const person = method === "ui/open-link" || (method === "tools/call" && params.name === "submit");',
  "    const timer = person ? 0 : setTimeout(",
  '      () => settle(id, (pending) => pending.refuse(failure("the host did not answer", { code: "timeout" }))),',
  `      ${ANSWER_WITHIN},`,
  "    );",
  "    waiting.set(id, { answer, refuse, timer });",
  "    post({ id, method, params });",
  "  });",
  "  window.host = {",
  "    request,",
  '    call: (name, args = {}) => request("tools/call", { name, arguments: args }),',
  "    notify: (method, params = {}) => post({ method, params }),",
  "    onAnswer: (hook) => { answered.push(hook); },",
  "    onContext: (hook) => { themed.push(hook); },",
  '    connect: () => connecting ||= request("ui/initialize", {}).then(',
  "      (result) => {",
  "        theme(result && result.hostContext);",
  '        post({ method: "ui/notifications/initialized", params: {} });',
  "        return result;",
  "      },",
  "      (error) => { connecting = null; throw error; },",
  "    ),",
  "  };",
  "})();",
].join("\n");

/** Said first, before the app's HTML: its document runs, whatever the app then does or draws. */
const STARTED = `parent.postMessage({ jsonrpc: "2.0", method: "${APP_STARTED}" }, "*");`;

/**
 * What went wrong in the app's document, said to the host, which shows it as plain text: an error
 * (a resource that didn't load among them), a refused promise, or a refusal of its policy, the
 * first five that differ by their message or what was refused, one kept for a thrown error, each
 * cut short (WebKit says the app's own errors only as "Script error."). And what it drew, 1.5 s
 * after the document loaded and, if nothing yet, again at 5 s, then once more when it first
 * does: its visible content, its largest visible canvas's size, the context the app asked of it,
 * and, for a 2D one alone, whether nine pixels on a 3 by 3 grid across it are transparent; the window, and
 * which of the APIs a game leans on it has. It said "nothing" only where both looks found no
 * visible text or element, and no canvas, one the app never drew on, or a 2D one transparent at
 * its centre. `getContext` is wrapped to remember which context each canvas was given, and the
 * sampler never asks a canvas for one it wasn't, so an app's later WebGL is left to it.
 *
 * The callbacks the app gives `requestAnimationFrame`, `setTimeout`, `setInterval` and
 * `addEventListener` are wrapped, so an error one throws is said by its own name, message and
 * first lines of its stack, where WebKit says only "Script error." of it, and is then thrown again
 * as it was: the app runs as it would. The window's report of an error said so isn't said again.
 * And where an uncaught error came while the app was animating, ten frames or more in the second
 * before it, whether any frame came in the 2 s after is said, as `stopped`, with that error, and
 * said again if frames come back: a frame loop that died with its error stopped the app. An app
 * that draws a frame now and then, on a tap, is never said to have stopped. Frames alone count,
 * never timers, which the sandbox's own scripts use. Nothing here is sent anywhere but the host's page, which
 * keeps none of it.
 */
const DIAGNOSED = [
  "(() => {",
  "  const said = new Set(), kinds = new WeakMap(), getContext = HTMLCanvasElement.prototype.getContext;",
  '  let errored = false, frames = 0, caughtAt = -1e9, probing = false, live = "", fault = null;',
  "  const recent = [], caught = new WeakSet(), guarded = new WeakMap(), now = () => performance.now();",
  "  const raw = { frame: requestAnimationFrame, timeout: setTimeout, add: EventTarget.prototype.addEventListener, remove: EventTarget.prototype.removeEventListener };",
  "  HTMLCanvasElement.prototype.getContext = function (type, ...rest) {",
  "    const context = getContext.call(this, type, ...rest);",
  "    if (context && !kinds.has(this)) kinds.set(this, String(type));",
  "    return context;",
  "  };",
  "  const offscreen = HTMLCanvasElement.prototype.transferControlToOffscreen;",
  "  if (offscreen) HTMLCanvasElement.prototype.transferControlToOffscreen = function (...rest) {",
  "    const handed = offscreen.apply(this, rest);",
  '    kinds.set(this, "offscreen");',
  "    return handed;",
  "  };",
  '  const cut = (text, most) => { try { return String(text == null ? "" : text).slice(0, most); } catch { return ""; } };',
  '  const post = (method, params) => parent.postMessage({ jsonrpc: "2.0", method, params }, "*");',
  "  const report = (params) => {",
  "    const key = params.blocked || params.message;",
  '    if (said.size >= 5 || said.has(key) || (params.kind !== "error" && !errored && said.size >= 4)) return;',
  '    if (params.kind === "error") errored = true;',
  "    said.add(key);",
  `    post("${APP_ERROR}", params);`,
  "  };",
  "  const lived = (stopped) => {",
  "    if (live === stopped) return;",
  "    live = stopped;",
  `    post("${APP_STOPPED}", { stopped, ...fault });`,
  "  };",
  "  const probe = (error) => {",
  '    if (probing || live === "yes" || recent.length < 10 || now() - recent[0] > 1000 || document.hidden) return;',
  "    probing = true;",
  "    fault = error;",
  "    const before = frames;",
  "    raw.timeout.call(window, () => {",
  "      probing = false;",
  '      if (!document.hidden) lived(frames > before ? "no" : "yes");',
  "    }, 2000);",
  "  };",
  "  const named = (error) => {",
  '    try { return error && typeof error === "object" && "message" in error ? (error.name || "Error") + ": " + error.message : String(error); }',
  '    catch { return "an error"; }',
  "  };",
  "  const failed = (error) => {",
  "    caughtAt = now();",
  "    try { caught.add(error); } catch {}",
  "    const message = named(error), lines = [];",
  '    try { for (const line of String(error.stack || "").split("\\n")) if (line.trim() && line.trim() !== message) lines.push(line.trim()); } catch {}',
  '    const found = { message: cut(message, 300), stack: cut(lines.slice(0, 4).join(" / "), 400) };',
  '    report({ kind: "error", ...found });',
  "    probe(found);",
  "  };",
  "  const guard = (callback) => function (...rest) {",
  "    try { return callback.apply(this, rest); } catch (error) { failed(error); throw error; }",
  "  };",
  "  window.requestAnimationFrame = (callback) => {",
  '    if (typeof callback !== "function") return raw.frame.call(window, callback);',
  "    const run = guard(callback);",
  "    return raw.frame.call(window, (time) => {",
  "      frames += 1;",
  "      recent.push(now());",
  "      if (recent.length > 10) recent.shift();",
  '      if (live === "yes") lived("no");',
  "      return run.call(window, time);",
  "    });",
  "  };",
  '  for (const name of ["setTimeout", "setInterval"]) {',
  "    const timer = window[name];",
  '    window[name] = (callback, ...rest) => timer.call(window, typeof callback === "function" ? guard(callback) : callback, ...rest);',
  "  }",
  "  EventTarget.prototype.addEventListener = function (type, listener, options) {",
  '    if (typeof listener === "function" && !guarded.has(listener)) guarded.set(listener, guard(listener));',
  "    return raw.add.call(this, type, guarded.get(listener) || listener, options);",
  "  };",
  "  EventTarget.prototype.removeEventListener = function (type, listener, options) {",
  "    return raw.remove.call(this, type, guarded.get(listener) || listener, options);",
  "  };",
  '  raw.add.call(window, "error", (event) => {',
  "    const target = event.target;",
  "    if (target && target !== window && target.tagName) {",
  '      report({ kind: "load", message: cut("<" + target.tagName.toLowerCase() + "> didn\'t load", 300), blocked: cut(target.currentSrc || target.src || target.href, 200) });',
  "      return;",
  "    }",
  '    if (caught.has(Object(event.error)) || (event.message === "Script error." && now() - caughtAt < 100)) return;',
  '    const message = cut(event.message || "an error", 300);',
  '    report({ kind: "error", message, source: cut(event.filename, 120), line: event.lineno | 0 });',
  "    probe({ message });",
  "  }, true);",
  '  raw.add.call(window, "unhandledrejection", (event) => {',
  '    let message = "a refused promise";',
  "    try { const reason = event.reason; message = cut(reason && reason.message ? reason.message : reason, 300); } catch {}",
  '    report({ kind: "rejection", message });',
  "  });",
  '  raw.add.call(document, "securitypolicyviolation", (event) => {',
  "    const directive = cut(event.effectiveDirective || event.violatedDirective, 60);",
  '    report({ kind: "policy", message: directive + " refused", directive, blocked: cut(event.blockedURI || "inline", 200), source: cut(event.sourceFile, 120), line: event.lineNumber | 0 });',
  "  });",
  "  const looked = () => {",
  "    const body = document.body;",
  "    let largest = null, content = false;",
  '    for (const each of body ? body.querySelectorAll("*") : []) {',
  "      const area = each.clientWidth * each.clientHeight || each.getBoundingClientRect().width * each.getBoundingClientRect().height;",
  '      if (each.tagName === "CANVAS") { if (area > 0 && (!largest || area > largest.clientWidth * largest.clientHeight)) largest = each; }',
  "      else if (area > 0 && each.childElementCount === 0 && !/^(SCRIPT|STYLE)$/.test(each.tagName)) content = true;",
  "    }",
  "    if (body && body.innerText.trim()) content = true;",
  '    const kind = largest ? kinds.get(largest) || "none" : "";',
  '    let pixels = "";',
  '    if (kind === "2d") {',
  "      try {",
  '        const context = largest.getContext("2d");',
  '        pixels = "blank";',
  "        for (const fx of [1, 2, 3]) for (const fy of [1, 2, 3]) {",
  "          const at = context.getImageData((largest.width * fx) >> 2, (largest.height * fy) >> 2, 1, 1).data;",
  '          if (at[3] !== 0) pixels = "drawn";',
  "        }",
  '      } catch { pixels = "unread"; }',
  "    }",
  '    const nothing = !content && (!largest || kind === "none" || pixels === "blank");',
  "    return { nothing, params: {",
  '      readyState: document.readyState, children: body ? body.childElementCount : 0, canvases: document.getElementsByTagName("canvas").length,',
  "      canvasWidth: largest ? largest.clientWidth : 0, canvasHeight: largest ? largest.clientHeight : 0, canvasContext: kind, canvasPixels: pixels,",
  "      width: innerWidth, height: innerHeight, pixelRatio: devicePixelRatio, userAgent: cut(navigator.userAgent, 120),",
  '      has: ["AudioContext", "webkitAudioContext", "ResizeObserver", "requestAnimationFrame"].filter((name) => name in window).join(" "),',
  "    } };",
  "  };",
  '  raw.add.call(window, "DOMContentLoaded", () => {',
  "    let first = true;",
  "    const sample = () => {",
  "      const { nothing, params } = looked();",
  `      post("${APP_BOOT}", { ...params, drawn: nothing ? (first ? "not yet" : "nothing") : "something" });`,
  "      if (!nothing || !first) {",
  "        if (nothing) {",
  `          const watch = setInterval(() => { if (!looked().nothing) { clearInterval(watch); post("${APP_BOOT}", { ...looked().params, drawn: "something" }); } }, 1000);`,
  "          setTimeout(() => clearInterval(watch), 120000);",
  "        }",
  "        return;",
  "      }",
  "      first = false;",
  "      setTimeout(sample, 3500);",
  "    };",
  "    setTimeout(sample, 1500);",
  "  });",
  "})();",
].join("\n");

/** The app's document: its own policy, no DNS prefetching, no WebRTC, its size and `host` first. */
export const appDocument = (html: string): string =>
  `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${APP_POLICY}"><meta http-equiv="x-dns-prefetch-control" content="off"><script>${STARTED}\n${DIAGNOSED}\n${NO_WEBRTC}\n${SIZED}\n${HOST}</script>${html}`;

/** What the app's frame may do: run its scripts, and nothing else. */
export const APP_SANDBOX = "allow-scripts";

/** Run the sandbox in `scope`, its page's window, if the portal at `?host=` frames it. */
export function startSandbox(scope: Window): void {
  // `?host=` is trusted because the sandbox's `frame-ancestors` names the portal alone, so no other
  // page can frame it; and it is only ever where messages go, never written into the page.
  const host = new URLSearchParams(scope.location.search).get("host");
  if (scope.parent === scope || host === null) {
    return; // not framed: nothing to run, and no one to tell
  }
  let app: HTMLIFrameElement | null = null;
  let tell: ((width: number, height: number) => void) | null = null;
  scope.addEventListener("message", (event) => {
    if (app !== null && event.source === app.contentWindow) {
      const text = relayed(sized(scope, app, event.data));
      if (text !== null) {
        scope.parent.postMessage(text, host);
      }
      return;
    }
    if (event.source !== scope.parent || event.origin !== host) {
      return;
    }
    if (app === null) {
      app = framed(scope.document, event.data);
      if (app !== null) {
        tell = fit(scope, app);
      }
      return;
    }
    if (isObject(event.data) && event.data.method === RESOURCE_READY) {
      return; // the host gives the app on every ready and load: the first one runs, alone
    }
    const size = viewport(event.data);
    if (size !== null) {
      tell?.(...size);
    }
    app.contentWindow?.postMessage(event.data, "*");
  });
  scope.parent.postMessage(JSON.stringify({ jsonrpc: "2.0", method: PROXY_READY }), host);
}

/** The app's frame, made from the portal's first message if it holds the app; null if not. */
function framed(document: Document, data: unknown): HTMLIFrameElement | null {
  if (!isObject(data) || data.method !== RESOURCE_READY || !isObject(data.params)) {
    return null;
  }
  const { html, title } = data.params;
  if (!isString(html)) {
    return null;
  }
  const frame = document.createElement("iframe");
  frame.setAttribute("sandbox", APP_SANDBOX);
  frame.setAttribute("referrerpolicy", "no-referrer");
  frame.title = isString(title) ? title : "An app";
  // Placed against the window, not in a body iOS may lay out at nothing; `fit` sizes it.
  frame.style.cssText = "position:absolute;inset:0;border:0";
  frame.srcdoc = appDocument(html);
  document.body.append(frame);
  return frame;
}

/** The app's frame's size where nothing measured it: the host's first height, a phone's width. */
const FLOOR = [320, 360] as const;

/**
 * The app's frame sized in pixels, never by percentages, now and whenever the sandbox's window
 * changes: on iOS the frame, sized by percentages, was laid out at 0 by 0, and an app that fits
 * its canvas to its window drew nothing to see. Each side is the window's, measured, or where it
 * measures 0, the size the host last said its frame is, or the last one measured, or `FLOOR`.
 * What it returns is how the host's size is said to it.
 */
export function fit(
  scope: Window,
  frame: HTMLIFrameElement,
): (width: number, height: number) => void {
  const root = scope.document.documentElement;
  let told: readonly [number, number] = [0, 0];
  let last = told;
  const size = () => {
    last = [
      root.clientWidth || scope.innerWidth || told[0] || last[0] || FLOOR[0],
      root.clientHeight || scope.innerHeight || told[1] || last[1] || FLOOR[1],
    ];
    frame.style.width = `${last[0]}px`;
    frame.style.height = `${last[1]}px`;
  };
  size();
  scope.addEventListener("resize", size);
  frame.addEventListener("load", size);
  const Observer = (scope as Window & { ResizeObserver?: typeof ResizeObserver }).ResizeObserver;
  if (Observer) {
    new Observer(size).observe(root);
  }
  return (width, height) => {
    told = [width, height];
    size();
  };
}

/** The host's frame's size, if `data` says it: its context's `viewport`, as given or answered. */
function viewport(data: unknown): [number, number] | null {
  const context = isObject(data)
    ? isObject(data.result) && isObject(data.result.hostContext)
      ? data.result.hostContext
      : data.method === "ui/notifications/host-context-changed" && data.params
    : null;
  const said = isObject(context) ? context.viewport : null;
  return isObject(said) && typeof said.width === "number" && typeof said.height === "number"
    ? [said.width, said.height]
    : null;
}

/**
 * The app's look at what it drew, with the sandbox's window and the app's frame as laid out, so a
 * blank frame says which of them was at nothing. They are the sandbox's: an app's own are replaced.
 */
function sized(scope: Window, frame: HTMLIFrameElement, data: unknown): unknown {
  if (!isObject(data) || data.method !== APP_BOOT || !isObject(data.params)) {
    return data;
  }
  const { width, height } = frame.getBoundingClientRect();
  const params = {
    ...data.params,
    sandboxWidth: scope.innerWidth,
    sandboxHeight: scope.innerHeight,
    frameWidth: width,
    frameHeight: height,
  };
  return { ...data, params };
}

/** What the app sent, as JSON text within `MOST_MESSAGE`; null for what can't be, dropped. */
function relayed(data: unknown): string | null {
  try {
    const text = JSON.stringify(data);
    return isString(text) && new TextEncoder().encode(text).length <= MOST_MESSAGE ? text : null;
  } catch {
    return null; // a cycle, a BigInt, or something else JSON can't hold
  }
}
