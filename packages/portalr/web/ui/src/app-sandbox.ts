/**
 * The sandbox: the page the portal frames on the apps' origin, which runs an agent's app in a
 * frame of its own (lattice RFC-0005, portalr ADR-0051). It is static and holds nothing. Framed by
 * the portal alone (its policy's `frame-ancestors`), it takes the app's HTML from its parent and
 * nothing from anyone else, and runs it in a frame sandboxed to an opaque origin with scripts and
 * nothing more: no forms, popups, top navigation or downloads, and no origin to read. The app's
 * document inherits the sandbox's policy, which loads nothing from anywhere, and begins with the
 * same policy of its own, DNS prefetching off, and WebRTC taken away, which no policy can refuse.
 * What the app sends is relayed to the portal as JSON text, within the size a message may be;
 * what the portal sends is relayed to the app.
 */

import { MOST_MESSAGE, PROXY_READY, RESOURCE_READY } from "./app-bridge";
import { isObject, isString } from "./json";

/** An app's policy, which the server sends for the sandbox too: `web/ui/csp/app-policy.txt`. */
export const APP_POLICY =
  "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; base-uri 'none'; form-action 'none'";

/**
 * Before the app's own script runs: every WebRTC constructor removed, since a peer connection's
 * ICE reaches any address over UDP and no policy refuses it in Chromium. A frame the app makes has
 * an opaque origin of its own, so it can't take them back from one.
 */
const NO_WEBRTC =
  "for(const k of Object.getOwnPropertyNames(globalThis))if(/^(webkit)?RTC/.test(k))delete globalThis[k];";

/** The app's document: its own policy, no DNS prefetching and no WebRTC first, then its HTML. */
export const appDocument = (html: string): string =>
  `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${APP_POLICY}"><meta http-equiv="x-dns-prefetch-control" content="off"><script>${NO_WEBRTC}</script>${html}`;

/** What the app's frame may do: run its scripts, and nothing else. */
export const APP_SANDBOX = "allow-scripts";

/** Run the sandbox in `scope`, its page's window, if the portal at `?host=` frames it. */
export function startSandbox(scope: Window): void {
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
