import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
  applyPatch,
  Bridge,
  type BridgeHost,
  CALLS_A_MINUTE,
  type JsonObject,
  Limiter,
  MOST_HEIGHT,
  MOST_MESSAGE,
  MOST_STATE,
  PatchRefused,
  PROXY_READY,
  readMessage,
  STATE_EVERY,
  StateKeeper,
  type Written,
} from "./app-bridge";

const ORIGIN = "https://apps.example.com";
const text = (message: unknown) => JSON.stringify(message);
const request = (id: number, method: string, params?: JsonObject) =>
  text({ jsonrpc: "2.0", id, method, ...(params && { params }) });

// ─── messages ────────────────────────────────────────────────────────────────

test("a request or a known notification, as JSON text, is read", () => {
  expect(readMessage(request(1, "tools/call", { name: "get_state" }))).toEqual({
    kind: "request",
    id: 1,
    method: "tools/call",
    params: { name: "get_state" },
  });
  expect(readMessage(text({ jsonrpc: "2.0", id: "a", method: "nope" }))).toMatchObject({
    kind: "request",
    method: "nope",
    params: {},
  });
  expect(readMessage(text({ jsonrpc: "2.0", method: PROXY_READY }))).toEqual({
    kind: "notification",
    method: PROXY_READY,
    params: {},
  });
});

test.each([
  ["an object, not text", { jsonrpc: "2.0", id: 1, method: "ui/initialize" }],
  ["text that isn't JSON", "{"],
  ["JSON that isn't an object", "[1]"],
  ["another version of JSON-RPC", text({ jsonrpc: "1.0", id: 1, method: "ui/initialize" })],
  ["no method", text({ jsonrpc: "2.0", id: 1 })],
  ["params that aren't an object", text({ jsonrpc: "2.0", id: 1, method: "x", params: [1] })],
  ["an id that is neither text nor a number", text({ jsonrpc: "2.0", id: {}, method: "x" })],
  ["an unknown notification", text({ jsonrpc: "2.0", method: "ui/notifications/evil" })],
  ["a message over the limit", request(1, "x", { pad: "x".repeat(MOST_MESSAGE) })],
])("%s is dropped", (_, data) => {
  expect(readMessage(data)).toBeNull();
});

test("a frame is answered sixty times a minute, then not until the minute moves on", () => {
  let now = 0;
  const limiter = new Limiter(CALLS_A_MINUTE, 60_000, () => now);
  expect(Array.from({ length: CALLS_A_MINUTE }, () => limiter.take()).every(Boolean)).toBe(true);
  expect(limiter.take()).toBe(false);
  now = 59_999;
  expect(limiter.take()).toBe(false);
  now = 60_000;
  expect(limiter.take()).toBe(true);
});

// ─── JSON Patch ───────────────────────────────────────────────────────────────

test("a patch's every operation applies to the state, which it never changes in place", () => {
  const state = { a: { b: 1 }, list: [1, 2], "x/y": "slash", "t~": 0 };
  const patched = applyPatch(state, [
    { op: "add", path: "/list/-", value: 3 },
    { op: "add", path: "/list/0", value: 0 },
    { op: "replace", path: "/a/b", value: 2 },
    { op: "copy", from: "/a", path: "/c" },
    { op: "move", from: "/x~1y", path: "/moved" },
    { op: "remove", path: "/t~0" },
    { op: "test", path: "/list", value: [0, 1, 2, 3] },
    { op: "replace", path: "/list/1", value: 9 },
  ]);
  expect(patched).toEqual({ a: { b: 2 }, list: [0, 9, 2, 3], c: { b: 2 }, moved: "slash" });
  expect(state).toEqual({ a: { b: 1 }, list: [1, 2], "x/y": "slash", "t~": 0 });
  expect(applyPatch(state, [{ op: "replace", path: "", value: { fresh: true } }])).toEqual({
    fresh: true,
  });
  expect(applyPatch({}, [{ op: "add", path: "", value: { whole: 1 } }])).toEqual({ whole: 1 });
});

test.each([
  ["no list", { op: "add", path: "/a", value: 1 }],
  ["an operation that isn't an object", [1]],
  ["an operation JSON Patch hasn't", [{ op: "merge", path: "/a" }]],
  ["no pointer", [{ op: "add", path: "a", value: 1 }]],
  ["a path to nothing", [{ op: "replace", path: "/missing", value: 1 }]],
  ["no parent", [{ op: "add", path: "/missing/deep", value: 1 }]],
  ["a parent that holds nothing", [{ op: "add", path: "/n/x", value: 1 }]],
  ["no index", [{ op: "add", path: "/list/7", value: 1 }]],
  ["an index that isn't one", [{ op: "remove", path: "/list/01" }]],
  ["a failed test", [{ op: "test", path: "/n", value: 2 }]],
  ["the state removed", [{ op: "remove", path: "" }]],
  ["a state that isn't an object", [{ op: "replace", path: "", value: [1] }]],
])("a patch with %s is refused whole", (_, patch) => {
  expect(() => applyPatch({ n: 1, list: [] }, patch)).toThrow(PatchRefused);
});

// ─── the state, coalesced ─────────────────────────────────────────────────────

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

/** A keeper whose writes end as `ends` says, recording each. */
function keeper(ends: Written[] = []) {
  const writes: { state: JsonObject; version: number }[] = [];
  const refusals: unknown[] = [];
  const kept = new StateKeeper(
    { state: { count: 0 }, version: 3 },
    (state, version) => {
      writes.push({ state, version });
      return Promise.resolve(ends.shift() ?? "done");
    },
    (rejection) => refusals.push(rejection),
    () => Date.now(),
  );
  return { kept, writes, refusals };
}

const add = (by: number) => [{ op: "replace", path: "/count", value: by }];

test("a state is written at once, then at most once every five seconds, coalesced", async () => {
  const { kept, writes } = keeper();
  expect(kept.set(add(1))).toEqual({ count: 1 });
  await vi.advanceTimersByTimeAsync(0);
  expect(writes).toEqual([{ state: { count: 1 }, version: 3 }]);
  kept.set(add(2));
  kept.set(add(3));
  await vi.advanceTimersByTimeAsync(STATE_EVERY - 1);
  expect(writes).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(writes.at(-1)).toEqual({ state: { count: 3 }, version: 4 });
  expect(kept.current).toEqual({ state: { count: 3 }, version: 5 });
  // The artifact's own version of what was written changes nothing.
  kept.rebase({ state: { count: 3 }, version: 5 });
  await vi.advanceTimersByTimeAsync(STATE_EVERY * 2);
  expect(writes).toHaveLength(2);
  kept.stop();
});

test("a write on a head that moved on waits for it, then writes the patches on it", async () => {
  const { kept, writes } = keeper(["stale"]);
  kept.set([{ op: "add", path: "/mine", value: true }]);
  await vi.advanceTimersByTimeAsync(STATE_EVERY * 3);
  expect(writes).toHaveLength(1);
  kept.rebase({ state: { count: 7 }, version: 4 });
  expect(kept.current).toEqual({ state: { count: 7, mine: true }, version: 4 });
  await vi.advanceTimersByTimeAsync(STATE_EVERY);
  expect(writes.at(-1)).toEqual({ state: { count: 7, mine: true }, version: 4 });
});

test("patches that no longer apply to a new head are dropped", () => {
  const { kept } = keeper(["stale"]);
  kept.set([{ op: "remove", path: "/count" }]);
  kept.rebase({ state: { other: 1 }, version: 9 });
  expect(kept.current).toEqual({ state: { other: 1 }, version: 9 });
  kept.rebase({ state: { older: 1 }, version: 2 });
  expect(kept.current.version).toBe(9);
  kept.stop();
});

test("a refused write puts the state back as the head has it, and says why", async () => {
  const { kept, writes, refusals } = keeper([{ refused: { type: "forbidden" } }]);
  kept.set(add(5));
  await vi.advanceTimersByTimeAsync(0);
  expect(writes).toHaveLength(1);
  expect(refusals).toEqual([{ type: "forbidden" }]);
  expect(kept.current).toEqual({ state: { count: 0 }, version: 3 });
});

test("a state past its limit is refused before anything is written", async () => {
  const { kept, writes } = keeper();
  expect(() => kept.set([{ op: "add", path: "/big", value: "x".repeat(MOST_STATE) }])).toThrow(
    PatchRefused,
  );
  await vi.advanceTimersByTimeAsync(STATE_EVERY);
  expect(writes).toEqual([]);
});

// ─── the bridge ───────────────────────────────────────────────────────────────

const SANDBOX = { name: "the sandbox's window" };

/** A bridge over a scripted host, and what it posted. */
function bridged(answers: { ask?: boolean; submitted?: string | null } = {}) {
  const posted: JsonObject[] = [];
  const asked: unknown[] = [];
  const opened: string[] = [];
  const sized: number[] = [];
  let quieted = 0;
  const host: BridgeHost = {
    app: () => ({ title: "Dice", html: "<p>1</p>" }),
    context: () => ({ theme: "dark" }),
    ask: (question) => {
      asked.push(question);
      return Promise.resolve(answers.ask ?? true);
    },
    submit: () => Promise.resolve(answers.submitted === undefined ? "sub_1" : answers.submitted),
    open: (url) => opened.push(url),
    resize: (height) => sized.push(height),
    quieted: () => {
      quieted += 1;
    },
  };
  const { kept, writes } = keeper();
  const bridge = new Bridge({
    source: SANDBOX,
    origin: ORIGIN,
    post: (message) => posted.push(message),
    host,
    state: kept,
  });
  const hear = async (data: unknown, from: unknown = SANDBOX, origin = ORIGIN) => {
    bridge.heard({ source: from, origin, data });
    await vi.advanceTimersByTimeAsync(0);
  };
  return { bridge, hear, posted, asked, opened, sized, writes, quiet: () => quieted };
}

test("a message from anything but the sandbox, at its origin, is dropped unanswered", async () => {
  const { hear, posted } = bridged();
  const asking = request(1, "ui/initialize");
  await hear(asking, { name: "another window" });
  await hear(asking, SANDBOX, "https://evil.example");
  await hear(asking, null);
  await hear(text({ jsonrpc: "2.0", id: 2, method: "tools/call" }).slice(1));
  expect(posted).toEqual([]);
});

test("the sandbox is given the app once it is ready, and the app the host's context", async () => {
  const { hear, posted, bridge } = bridged();
  await hear(text({ jsonrpc: "2.0", method: PROXY_READY }));
  await hear(request(1, "ui/initialize", { protocolVersion: "2026-01-26" }));
  bridge.contextChanged();
  expect(posted).toEqual([
    {
      jsonrpc: "2.0",
      method: "ui/notifications/sandbox-resource-ready",
      params: { title: "Dice", html: "<p>1</p>" },
    },
    {
      jsonrpc: "2.0",
      id: 1,
      result: {
        protocolVersion: "2026-01-26",
        hostInfo: { name: "portalr" },
        hostCapabilities: { openLinks: {}, serverTools: {} },
        hostContext: { theme: "dark" },
      },
    },
    { jsonrpc: "2.0", method: "ui/notifications/host-context-changed", params: { theme: "dark" } },
  ]);
});

test("an app reaches its own state, and no other tool or method", async () => {
  const { hear, posted, writes } = bridged();
  await hear(request(1, "tools/call", { name: "get_state" }));
  await hear(request(2, "tools/call", { name: "set_state", arguments: { patch: add(4) } }));
  await hear(request(3, "tools/call", { name: "set_state", arguments: { patch: "no" } }));
  await hear(request(4, "tools/call", { name: "create_artifact", arguments: {} }));
  await hear(request(5, "resources/read", { uri: "ui://other" }));
  expect(posted[0]).toMatchObject({ id: 1, result: { structuredContent: { version: 3 } } });
  expect(posted[1]).toMatchObject({
    id: 2,
    result: { structuredContent: { state: { count: 4 } } },
  });
  expect(posted[2]).toMatchObject({ id: 3, result: { isError: true } });
  expect(posted[3]).toMatchObject({
    id: 4,
    result: { isError: true, content: [{ text: "create_artifact is no tool of this app's" }] },
  });
  expect(posted[4]).toMatchObject({ id: 5, error: { code: -32601 } });
  expect(writes).toEqual([{ state: { count: 4 }, version: 3 }]);
});

test("a submission is sent only once the person confirms it, and said if it wasn't", async () => {
  const values = { rolled: 6 };
  const call = (id: number) => request(id, "tools/call", { name: "submit", arguments: { values } });
  const sent = bridged();
  await sent.hear(call(1));
  await sent.hear(request(2, "tools/call", { name: "submit", arguments: { values: [1] } }));
  expect(sent.asked).toEqual([{ kind: "submit", values }]);
  expect(sent.posted[0]).toMatchObject({
    result: { structuredContent: { submitted: true, id: "sub_1" } },
  });
  expect(sent.posted[1]).toMatchObject({ result: { isError: true } });
  const declined = bridged({ ask: false });
  await declined.hear(call(1));
  expect(declined.posted[0]).toMatchObject({
    result: { isError: true, content: [{ text: "The person didn't send it." }] },
  });
  const refused = bridged({ submitted: null });
  await refused.hear(call(1));
  expect(refused.posted[0]).toMatchObject({ result: { isError: true } });
});

test("a link opens only once the person confirms it, and only a web or mail address", async () => {
  const open = (id: number, url: string) => request(id, "ui/open-link", { url });
  const { hear, posted, asked, opened } = bridged();
  await hear(open(1, "https://example.com/docs?q=1"));
  await hear(open(2, "javascript:alert(1)"));
  await hear(open(3, "mailto:ops@example.com"));
  await hear(request(4, "ui/open-link", {}));
  expect(opened).toEqual(["https://example.com/docs?q=1", "mailto:ops@example.com"]);
  expect(asked).toHaveLength(2);
  expect(posted.map((each) => ("error" in each ? each.error : each.result))).toEqual([
    {},
    { code: -32602, message: "Only an http, https or mailto link opens." },
    {},
    { code: -32602, message: "Only an http, https or mailto link opens." },
  ]);
  const declined = bridged({ ask: false });
  await declined.hear(open(1, "https://example.com"));
  expect(declined.opened).toEqual([]);
  expect(declined.posted[0]).toMatchObject({ error: { code: -32000 } });
});

test("a frame is sized as its app asks, up to the most; a height too small to be one is none", async () => {
  const { hear, sized } = bridged();
  const size = (height: unknown) =>
    hear(text({ jsonrpc: "2.0", method: "ui/notifications/size-changed", params: { height } }));
  await size(0);
  await size(480.4);
  await size(5);
  await size(1e9);
  await size("tall");
  await hear(text({ jsonrpc: "2.0", method: "ui/notifications/initialized" }));
  expect(sized).toEqual([480, MOST_HEIGHT]);
});

test("the sandbox's measure sizes a frame until the app says its own height", async () => {
  const { hear, sized } = bridged();
  const size = (height: number, measured?: boolean) =>
    hear(
      text({
        jsonrpc: "2.0",
        method: "ui/notifications/size-changed",
        params: measured ? { height, measured } : { height },
      }),
    );
  await size(500, true);
  await size(0);
  await size(640, true);
  await size(700);
  await size(300, true);
  expect(sized).toEqual([500, 640, 700]);
});

test("past sixty messages in a minute, the frame isn't answered, and the page is told", async () => {
  const { hear, posted, quiet } = bridged();
  for (let id = 0; id < CALLS_A_MINUTE + 5; id += 1) {
    await hear(request(id, "tools/call", { name: "get_state" }));
  }
  expect(posted).toHaveLength(CALLS_A_MINUTE);
  expect(quiet()).toBe(5);
  await vi.advanceTimersByTimeAsync(60_000);
  await hear(request(99, "tools/call", { name: "get_state" }));
  expect(posted.at(-1)).toMatchObject({ id: 99 });
});
