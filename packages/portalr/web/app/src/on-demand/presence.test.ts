import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ghostsNow, type Heard, watchPresence } from "./presence";

/** A WebSocket the test plays the server of: what the canvas sent, and frames to answer with. */
class Socket {
  static made: Socket[] = [];
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  readonly url: string;
  constructor(url: string) {
    this.url = url;
    Socket.made.push(this);
  }
  send(text: string) {
    this.sent.push(JSON.parse(text));
  }
  close(code = 1006) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
  opened() {
    this.readyState = 1;
    this.onopen?.();
  }
  frame(frame: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
  said() {
    return this.sent.filter((frame) => frame.type === "presence");
  }
}

const peer = (name: string, seq: number, more: Record<string, unknown> = {}) => ({
  type: "peer_presence",
  artifact_id: "d1",
  peer: `p-${name}`,
  actor: { type: "user", id: name, name },
  seq,
  base_version: 1,
  ...more,
});

let heard: Heard[];

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", { OPEN: 1 });
  Socket.made = [];
  heard = [];
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function watched() {
  const presence = watchPresence(
    { url: () => "ws://portal.test/stream" },
    "d1",
    (now) => heard.push(now),
    (url) => new Socket(url) as unknown as WebSocket,
  );
  const socket = Socket.made.at(-1) as Socket;
  socket.opened();
  socket.frame({ type: "welcome", head_seq: 0 });
  socket.frame({ type: "replay_complete", up_to_seq: 0 });
  return { presence, socket };
}

const said = {
  baseVersion: 1,
  pointer: { x: 1, y: 2, tool: "pointer" as const, button: "down" as const },
  selection: ["a"],
  editing: [{ id: "a", type: "rectangle" }],
};

test("a canvas says hello for no thread, watches its diagram, and says where it is once allowed", () => {
  const { presence, socket } = watched();
  expect(socket.sent[0]).toMatchObject({ type: "hello", from_head: true, events: false });
  expect(socket.sent[1]).toMatchObject({
    type: "command",
    command: { type: "watch_artifact", artifact_id: "d1" },
  });
  presence.say(said);
  vi.advanceTimersByTime(100);
  expect(socket.said()).toEqual([]); // nothing is said before the watch is accepted
  socket.frame({ type: "command_result", outcome: { type: "watching", rights: "edit" } });
  expect(socket.said()).toHaveLength(1);
  expect(socket.said()[0]).toMatchObject({ seq: 1, base_version: 1, editing: said.editing });
  expect(heard.at(-1)?.rights).toBe("edit");
  presence.close();
});

test("at most twenty frames a second, and one every five while still", () => {
  const { presence, socket } = watched();
  socket.frame({ type: "command_result", outcome: { type: "watching", rights: "edit" } });
  for (let at = 0; at < 100; at += 1) {
    presence.say({ ...said, pointer: { ...said.pointer, x: at } });
    vi.advanceTimersByTime(10);
  }
  const sent = socket.said().length;
  expect(sent).toBeLessThanOrEqual(22);
  expect(socket.said().at(-1)?.pointer).toMatchObject({ x: 99 });
  vi.advanceTimersByTime(8_000);
  expect(socket.said().length).toBeGreaterThan(sent);
  presence.close();
});

test("a viewer says nothing it is changing, and a frame too large leaves it out", () => {
  const { presence, socket } = watched();
  socket.frame({ type: "command_result", outcome: { type: "watching", rights: "view" } });
  presence.say(said);
  vi.advanceTimersByTime(100);
  expect(socket.said().at(-1)?.editing).toEqual([]);
  socket.frame({ type: "command_result", outcome: { type: "watching", rights: "edit" } });
  presence.say({ ...said, editing: [{ id: "a", text: "x".repeat(70_000) }] });
  vi.advanceTimersByTime(100);
  expect(socket.said().at(-1)?.editing).toEqual([]);
  presence.close();
});

test("the others are heard as they come and go, and a watch that ends shows no one", () => {
  const { presence, socket } = watched();
  socket.frame({
    type: "command_result",
    outcome: { type: "watching", rights: "edit", peer: "p-me" },
  });
  socket.frame(peer("bob", 1));
  socket.frame(peer("carol", 1));
  socket.frame({ ...peer("dan", 1), artifact_id: "d9" });
  expect([...(heard.at(-1)?.peers.keys() ?? [])]).toEqual(["p-bob", "p-carol"]);
  socket.frame({ type: "peer_left", artifact_id: "d1", peer: "p-bob" });
  socket.frame({ type: "peer_left", artifact_id: "d1", peer: "p-nobody" });
  expect([...(heard.at(-1)?.peers.keys() ?? [])]).toEqual(["p-carol"]);
  // Its own peer leaving is its watch ending; an error, whatever it says, changes nothing.
  socket.frame({ type: "error", message: "a watch ended" });
  expect(heard.at(-1)?.rights).toBe("edit");
  socket.frame({ type: "peer_left", artifact_id: "d1", peer: "p-me" });
  expect(heard.at(-1)).toEqual({ peers: new Map(), rights: null });
  socket.frame({ type: "command_result", outcome: { type: "recorded" } });
  socket.frame({ type: "command_result", outcome: null });
  presence.close();
});

test("a dropped connection connects again, and watches again", () => {
  const { presence, socket } = watched();
  socket.frame({ type: "command_result", outcome: { type: "watching", rights: "edit" } });
  socket.frame(peer("bob", 1));
  socket.close();
  expect(heard.at(-1)?.peers.size).toBe(0);
  vi.advanceTimersByTime(600);
  const again = Socket.made.at(-1) as Socket;
  expect(again).not.toBe(socket);
  again.opened();
  again.frame({ type: "replay_complete", up_to_seq: 0 });
  expect(again.sent.at(-1)).toMatchObject({ command: { type: "watch_artifact" } });
  for (const _ of [1, 2, 3, 4, 5]) {
    again.close();
    vi.advanceTimersByTime(5_000);
  }
  presence.close();
  const last = Socket.made.at(-1) as Socket;
  last.onclose?.({ code: 1000 }); // closed for good: nothing connects again
  vi.advanceTimersByTime(10_000);
  expect(Socket.made.at(-1)).toBe(last);
});

test("a peer's picture stays until a revision newer than the one it drew on arrives", () => {
  const drawn = { peer: "p", name: "Bob", baseVersion: 3, elements: [{ id: "a" } as never] };
  const stopped = { ...drawn, elements: [] };
  const now = ghostsNow(new Map(), [drawn], 3);
  expect(now.get("p")).toBe(drawn);
  expect(ghostsNow(now, [stopped], 3).get("p")).toBe(drawn);
  expect(ghostsNow(now, [stopped], 4).has("p")).toBe(false);
  expect(ghostsNow(now, [], 3).has("p")).toBe(false); // a peer that left is gone
  expect(ghostsNow(new Map(), [stopped], 3).size).toBe(0);
});

test("a connection refused for good isn't asked again", () => {
  const { presence, socket } = watched();
  socket.close(4404);
  vi.advanceTimersByTime(10_000);
  expect(Socket.made.at(-1)).toBe(socket);
  presence.close();
});
