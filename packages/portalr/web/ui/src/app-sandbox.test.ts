import { expect, test, vi } from "vitest";
import POLICY from "../csp/app-policy.txt?raw";
import { APP_BOOT, MOST_MESSAGE, PROXY_READY, RESOURCE_READY } from "./app-bridge";
import { APP_POLICY, APP_SANDBOX, appDocument, fit, startSandbox } from "./app-sandbox";

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
    innerWidth: 390,
    innerHeight: 0,
    document: {
      createElement: document.createElement.bind(document),
      body,
      documentElement: { clientWidth: 0, clientHeight: 0 },
    },
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

test("a sandbox runs the first app it is given, and passes no later one to it", () => {
  const { parent, body, hear } = scope();
  const source = parent as unknown as Window;
  const given = { jsonrpc: "2.0", method: RESOURCE_READY, params: { html: "<b>" } };
  const sent = vi.fn();
  const app = vi.spyOn(HTMLIFrameElement.prototype, "contentWindow", "get");
  app.mockReturnValue({ postMessage: sent } as unknown as Window);
  hear({ source, origin: PORTAL, data: given });
  const frame = body.querySelector("iframe") as HTMLIFrameElement;
  hear({ source, origin: PORTAL, data: { ...given, params: { html: "<i>" } } });
  const context = { jsonrpc: "2.0", method: "ui/notifications/host-context-changed", params: {} };
  hear({ source, origin: PORTAL, data: context });
  expect(body.querySelectorAll("iframe")).toHaveLength(1);
  expect(sent.mock.calls).toEqual([[context, "*"]]);
  app.mockRestore();
  frame.remove();
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

test("the app's look at what it drew carries the sandbox's window and the app's frame", () => {
  const { posted, parent, body, hear } = scope();
  hear({
    source: parent as unknown as Window,
    origin: PORTAL,
    data: { jsonrpc: "2.0", method: RESOURCE_READY, params: { html: "" } },
  });
  const frame = body.querySelector("iframe") as HTMLIFrameElement;
  const app = frame.contentWindow as Window;
  vi.spyOn(frame, "getBoundingClientRect").mockReturnValue(new DOMRect(0, 0, 390, 0));
  hear({ source: app, data: { method: APP_BOOT, params: { drawn: "nothing", frameWidth: 9 } } });
  expect(JSON.parse(posted.at(-1)?.[0] as string).params).toEqual({
    drawn: "nothing",
    sandboxWidth: 390,
    sandboxHeight: 0,
    frameWidth: 390,
    frameHeight: 0,
  });
  frame.remove();
});

test("a sandbox given an app that isn't one makes no frame", () => {
  const { parent, body, hear } = scope();
  const source = parent as unknown as Window;
  hear({ source, origin: PORTAL, data: { method: RESOURCE_READY, params: { html: 1 } } });
  hear({ source, origin: PORTAL, data: { method: RESOURCE_READY } });
  hear({ source, origin: PORTAL, data: "text" });
  expect(body.querySelector("iframe")).toBeNull();
});

/** A window measured at `width` by `height`, its resize listeners and observers to run by hand. */
function measured(width: number, height: number) {
  const resized: (() => void)[] = [];
  const observed: (() => void)[] = [];
  const root = { clientWidth: width, clientHeight: height };
  class Observer {
    constructor(run: () => void) {
      observed.push(run);
    }
    observe() {}
  }
  const scope = {
    document: { documentElement: root },
    innerWidth: 0,
    innerHeight: 0,
    ResizeObserver: Observer,
    addEventListener: (_: string, run: () => void) => resized.push(run),
  };
  const frame = document.createElement("iframe");
  const tell = fit(scope as unknown as Window, frame);
  const size = () => [frame.style.width, frame.style.height];
  return { root, scope, frame, resized, observed, tell, size };
}

test("the app's frame is sized to the sandbox's window in pixels, and follows it", () => {
  const { root, frame, resized, observed } = measured(390, 360);
  expect([frame.style.width, frame.style.height]).toEqual(["390px", "360px"]);
  root.clientHeight = 500;
  resized[0]?.();
  expect(frame.style.height).toBe("500px");
  root.clientWidth = 320;
  observed[0]?.();
  expect(frame.style.width).toBe("320px");
});

test("a window measured at nothing falls back to the floor, never to 0", () => {
  expect(measured(0, 0).size()).toEqual(["320px", "360px"]);
});

test("a window measured at nothing falls back to the last size it measured", () => {
  const { root, resized, size } = measured(390, 500);
  root.clientWidth = 0;
  root.clientHeight = 0;
  resized[0]?.();
  expect(size()).toEqual(["390px", "500px"]);
});

test("a window measured at nothing falls back to the size the host says its frame is", () => {
  const { root, resized, tell, size } = measured(390, 500);
  root.clientWidth = 0;
  root.clientHeight = 0;
  tell(412, 640);
  expect(size()).toEqual(["412px", "640px"]);
  root.clientWidth = 375;
  resized[0]?.();
  expect(size()).toEqual(["375px", "640px"]);
});

test("the host's viewport, given or answered, is told to the frame's size", () => {
  const { parent, body, hear } = scope();
  const source = parent as unknown as Window;
  hear({ source, origin: PORTAL, data: { method: RESOURCE_READY, params: { html: "" } } });
  const frame = body.querySelector("iframe") as HTMLIFrameElement;
  const viewport = { width: 412, height: 640 };
  expect([frame.style.width, frame.style.height]).toEqual(["390px", "360px"]);
  hear({ source, origin: PORTAL, data: { id: 1, result: { hostContext: { viewport } } } });
  expect([frame.style.width, frame.style.height]).toEqual(["390px", "640px"]);
  const changed = "ui/notifications/host-context-changed";
  hear({ source, origin: PORTAL, data: { method: changed, params: { viewport: { width: "x" } } } });
  hear({
    source,
    origin: PORTAL,
    data: { method: changed, params: { viewport: { ...viewport, height: 700 } } },
  });
  expect(frame.style.height).toBe("700px");
  frame.remove();
});
