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
 * first five that differ by their message, each cut short; and once, 1.5 s after the document
 * loaded, what it drew: its children and canvases, the largest canvas's size and whether an 8 by 8
 * copy of it is blank, the window, and which of the APIs a game leans on it has. The canvas is
 * copied, never asked for a context of its own, so an app's WebGL or 2D context is left as it is.
 * Nothing here is sent anywhere but the host's page, which keeps none of it.
 */
const DIAGNOSED = [
  "(() => {",
  "  const said = new Set();",
  '  const cut = (text, most) => String(text == null ? "" : text).slice(0, most);',
  "  const report = (params) => {",
  "    if (said.size >= 5 || said.has(params.message)) return;",
  "    said.add(params.message);",
  `    parent.postMessage({ jsonrpc: "2.0", method: "${APP_ERROR}", params }, "*");`,
  "  };",
  '  addEventListener("error", (event) => {',
  "    const target = event.target;",
  "    if (target && target !== window && target.tagName) {",
  '      const blocked = target.currentSrc || target.src || target.href || "";',
  '      report({ kind: "load", message: cut("<" + target.tagName.toLowerCase() + "> didn\'t load", 300), blocked: cut(blocked, 200) });',
  "      return;",
  "    }",
  '    report({ kind: "error", message: cut(event.message || "an error", 300), source: cut(event.filename, 120), line: event.lineno | 0 });',
  "  }, true);",
  '  addEventListener("unhandledrejection", (event) => {',
  "    const reason = event.reason;",
  '    report({ kind: "rejection", message: cut(reason && reason.message ? reason.message : reason, 300) });',
  "  });",
  '  document.addEventListener("securitypolicyviolation", (event) => {',
  '    report({ kind: "policy", message: cut(event.effectiveDirective + " refused " + (event.blockedURI || "inline"), 300), directive: cut(event.effectiveDirective || event.violatedDirective, 60), blocked: cut(event.blockedURI, 200), source: cut(event.sourceFile, 120), line: event.lineNumber | 0 });',
  "  });",
  '  addEventListener("DOMContentLoaded", () => setTimeout(() => {',
  "    let largest = null;",
  '    const canvases = document.querySelectorAll("canvas");',
  "    for (const each of canvases) if (!largest || each.clientWidth * each.clientHeight > largest.clientWidth * largest.clientHeight) largest = each;",
  '    let canvasPixels = "none";',
  "    if (largest) {",
  "      try {",
  '        const copy = document.createElement("canvas");',
  "        copy.width = copy.height = 8;",
  '        const context = copy.getContext("2d");',
  "        context.drawImage(largest, 0, 0, 8, 8);",
  "        const data = context.getImageData(0, 0, 8, 8).data;",
  "        let blank = true;",
  "        for (let i = 0; i < data.length; i += 4) if (data[i + 3] !== 0 && !(data[i] > 249 && data[i + 1] > 249 && data[i + 2] > 249)) blank = false;",
  '        canvasPixels = blank ? "blank" : "drawn";',
  '      } catch { canvasPixels = "unread"; }',
  "    }",
  '    const has = ["AudioContext", "webkitAudioContext", "ResizeObserver", "requestAnimationFrame"].filter((name) => name in window).join(" ");',
  `    parent.postMessage({ jsonrpc: "2.0", method: "${APP_BOOT}", params: {`,
  "      readyState: document.readyState,",
  "      children: document.body ? document.body.childElementCount : 0,",
  "      canvases: canvases.length,",
  "      canvasWidth: largest ? largest.clientWidth : 0,",
  "      canvasHeight: largest ? largest.clientHeight : 0,",
  "      canvasPixels, width: innerWidth, height: innerHeight, pixelRatio: devicePixelRatio,",
  "      userAgent: cut(navigator.userAgent, 120), has,",
  '    } }, "*");',
  "  }, 1500));",
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
  scope.addEventListener("message", (event) => {
    if (app !== null && event.source === app.contentWindow) {
      const text = relayed(event.data);
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
      return;
    }
    if (isObject(event.data) && event.data.method === RESOURCE_READY) {
      return; // the host gives the app on every ready and load: the first one runs, alone
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
  frame.style.cssText = "display:block;width:100%;height:100%;border:0";
  frame.srcdoc = appDocument(html);
  document.body.append(frame);
  return frame;
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
