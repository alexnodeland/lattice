import { expect, test } from "vitest";
import POLICY from "../csp/app-policy.txt?raw";
import { MOST_MESSAGE, PROXY_READY, RESOURCE_READY } from "./app-bridge";
import { APP_POLICY, APP_SANDBOX, appDocument, startSandbox } from "./app-sandbox";

const PORTAL = "https://app.example.com";

test("the app's own policy is the one the server sends for the sandbox", () => {
  expect(APP_POLICY).toBe(POLICY.trim());
});

test("the app's document begins with its policy, no DNS prefetching and no WebRTC", () => {
  const document = appDocument("<p>Hi</p>");
  const parsed = new DOMParser().parseFromString(document, "text/html");
  const [policy, prefetch] = parsed.head.querySelectorAll("meta[http-equiv]");
  expect(policy?.getAttribute("content")).toBe(APP_POLICY);
  expect(prefetch?.getAttribute("content")).toBe("off");
  expect(parsed.querySelector("script")?.textContent).toContain("RTC");
  expect(document.endsWith("<p>Hi</p>")).toBe(true);
  expect(APP_SANDBOX).toBe("allow-scripts");
});

/** A sandbox page's window, framed by `parent` at `?host=`, and what it was sent and made. */
function scope({ framed = true, search = `?host=${encodeURIComponent(PORTAL)}` } = {}) {
  const posted: [unknown, string][] = [];
  const parent = { postMessage: (data: unknown, to: string) => posted.push([data, to]) };
  const listeners: ((event: Partial<MessageEvent>) => void)[] = [];
  const body = document.createElement("div");
  const window: Record<string, unknown> = {
    location: { search },
    document: { createElement: document.createElement.bind(document), body },
    addEventListener: (_: string, listener: (event: Partial<MessageEvent>) => void) =>
      listeners.push(listener),
  };
  window.parent = framed ? parent : window;
  startSandbox(window as unknown as Window);
  const hear = (event: Partial<MessageEvent>) => {
    for (const listener of listeners) {
      listener(event);
    }
  };
  return { posted, parent, body, hear, listening: () => listeners.length };
}

test("a sandbox no one frames, or framed with no host named, runs nothing", () => {
  expect(scope({ framed: false }).listening()).toBe(0);
  expect(scope({ search: "" }).listening()).toBe(0);
});

test("a framed sandbox says it is ready, to its host alone, and runs the app it is given", () => {
  const { posted, parent, body, hear } = scope();
  expect(posted).toEqual([[JSON.stringify({ jsonrpc: "2.0", method: PROXY_READY }), PORTAL]]);
  const given = { jsonrpc: "2.0", method: RESOURCE_READY, params: { title: "Dice", html: "<b>" } };
  hear({ source: { another: "window" } as unknown as Window, origin: PORTAL, data: given });
  hear({ source: parent as unknown as Window, origin: "https://evil.example", data: given });
  hear({ source: parent as unknown as Window, origin: PORTAL, data: { method: "other" } });
  expect(body.querySelector("iframe")).toBeNull();
  hear({ source: parent as unknown as Window, origin: PORTAL, data: given });
  const frame = body.querySelector("iframe");
  expect(frame?.getAttribute("sandbox")).toBe("allow-scripts");
  expect(frame?.title).toBe("Dice");
  expect(frame?.srcdoc).toBe(appDocument("<b>"));
  frame?.remove();
});

test("the app's messages reach the host as JSON text within the limit; others are dropped", () => {
  const { posted, parent, body, hear } = scope();
  const given = { jsonrpc: "2.0", method: RESOURCE_READY, params: { html: "" } };
  hear({ source: parent as unknown as Window, origin: PORTAL, data: given });
  const frame = body.querySelector("iframe");
  const app = frame?.contentWindow as Window;
  expect(frame?.title).toBe("An app");
  const cycle: Record<string, unknown> = {};
  cycle.self = cycle;
  hear({ source: app, origin: "null", data: { jsonrpc: "2.0", id: 1, method: "ui/initialize" } });
  hear({ source: app, origin: "null", data: cycle });
  hear({ source: app, origin: "null", data: { pad: "x".repeat(MOST_MESSAGE) } });
  hear({ source: app, origin: "null", data: undefined });
  expect(posted.slice(1)).toEqual([
    [JSON.stringify({ jsonrpc: "2.0", id: 1, method: "ui/initialize" }), PORTAL],
  ]);
  frame?.remove();
});

test("a sandbox given an app that isn't one makes no frame", () => {
  const { parent, body, hear } = scope();
  const source = parent as unknown as Window;
  hear({ source, origin: PORTAL, data: { method: RESOURCE_READY, params: { html: 1 } } });
  hear({ source, origin: PORTAL, data: { method: RESOURCE_READY } });
  hear({ source, origin: PORTAL, data: "text" });
  expect(body.querySelector("iframe")).toBeNull();
});
