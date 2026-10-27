import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { type ArtifactrStream, artifactr, type Workspace } from "./artifactr";
import type * as v1 from "./generated/artifactr.v1";
import { Stream, type StreamOptions } from "./stream";
import { ScriptedServer } from "./test/server";
import { until } from "./test/until";

let server: ScriptedServer;
let stream: ArtifactrStream;

beforeEach(() => {
  server = new ScriptedServer();
});

afterEach(() => {
  stream?.close();
  server.stop();
});

function open(options: Partial<StreamOptions<v1.Hello>> = {}, state?: Workspace): ArtifactrStream {
  stream = new Stream(artifactr, { url: () => server.url, ...options }, state);
  stream.open();
  return stream;
}

/** Every `seq` the store applies, in the order it applies them. */
function applied(store: ArtifactrStream): number[] {
  const seqs: number[] = [];
  store.subscribe(() => {
    const { seq } = store.snapshot();
    if (seq !== seqs.at(-1) && seq !== 0) {
      seqs.push(seq);
    }
  });
  return seqs;
}

const message = (n: number) => ({
  type: "message_posted",
  thread_id: "thr_1",
  message_id: `msg_${n}`,
  content: `message ${n}`,
});

const ids = (store: ArtifactrStream) =>
  store.snapshot().state.threads.thr_1?.messages.map((m) => m.id) ?? [];

test("a store replays the log, then goes live", async () => {
  server.append({ type: "thread_created", thread_id: "thr_1", title: "Launch" });
  server.append(message(1));
  open({ hello: { threads: ["thr_1"] } });
  await until(stream, (s) => s.status === "live");
  server.append(message(2));
  await until(stream, (s) => s.seq === 3);
  expect(stream.snapshot().state.threads.thr_1?.title).toBe("Launch");
  expect(ids(stream)).toEqual(["msg_1", "msg_2"]);
  expect(server.hellos).toEqual([
    { type: "hello", protocol: "artifactr.v1", resume_after_seq: 0, threads: ["thr_1"] },
  ]);
});

test("a live event is heard, and the replay before it isn't", async () => {
  server.append(message(1));
  open();
  const heard: number[] = [];
  const stop = stream.onLiveEvent((envelope) => heard.push(envelope.seq));
  await until(stream, (s) => s.status === "live" && s.seq === 1);
  server.append(message(2));
  await until(stream, (s) => s.seq === 2);
  stop();
  server.append(message(3));
  await until(stream, (s) => s.seq === 3);
  expect(heard).toEqual([2]);
});

test("a store resumes across a dropped connection without losing or repeating an event", async () => {
  open();
  const seqs = applied(stream);
  await until(stream, (s) => s.status === "live");
  for (const n of [1, 2, 3]) {
    server.append(message(n));
  }
  await until(stream, (s) => s.seq === 3);
  server.drop();
  await until(stream, (s) => s.status === "connecting");
  // Committed while the client was away.
  server.append(message(4));
  server.append(message(5));
  await until(stream, (s) => s.status === "live" && s.seq === 5);
  server.append(message(6));
  await until(stream, (s) => s.seq === 6);
  expect(seqs).toEqual([1, 2, 3, 4, 5, 6]);
  expect(ids(stream)).toEqual([1, 2, 3, 4, 5, 6].map((n) => `msg_${n}`));
  expect(server.hellos.map((hello) => hello.resume_after_seq)).toEqual([0, 3]);
});

test("an event sent twice is applied once", async () => {
  server.append(message(1));
  open();
  await until(stream, (s) => s.status === "live" && s.seq === 1);
  server.append(message(2));
  server.repeat(1);
  server.repeat(2);
  server.append(message(3));
  await until(stream, (s) => s.seq === 3);
  expect(ids(stream)).toEqual(["msg_1", "msg_2", "msg_3"]);
});

test("a store resumes after a tail it read over REST, and skips what it already has", async () => {
  for (const n of [1, 2, 3]) {
    server.append(message(n));
  }
  const tail = [1, 2].reduce(
    (state, n) =>
      artifactr.apply(state, {
        type: "event",
        seq: n,
        id: `evt_${n}`,
        ts: "2026-10-12T00:00:00Z",
        workspace_id: "ws_1",
        actor: { kind: "user", id: "alice" },
        event: message(n) as v1.MessagePosted,
      }),
    artifactr.initial(),
  );
  open({ after: 2 }, tail);
  await until(stream, (s) => s.status === "live" && s.seq === 3);
  expect(ids(stream)).toEqual(["msg_1", "msg_2", "msg_3"]);
  expect(server.hellos[0]?.resume_after_seq).toBe(2);
});

test("a store that starts at the head replays nothing, and resumes from the head", async () => {
  server.append(message(1));
  server.append(message(2));
  open({ fromHead: true });
  await until(stream, (s) => s.status === "live" && s.seq === 2);
  expect(ids(stream)).toEqual([]);
  server.append(message(3));
  await until(stream, (s) => s.seq === 3);
  server.drop();
  await server.hello(2);
  await until(stream, (s) => s.status === "live");
  expect(server.hellos).toEqual([
    { type: "hello", protocol: "artifactr.v1", from_head: true },
    { type: "hello", protocol: "artifactr.v1", resume_after_seq: 3 },
  ]);
  expect(ids(stream)).toEqual(["msg_3"]);
});

test("a store told to reset discards what it holds and rebuilds from the replay", async () => {
  for (const n of [1, 2, 3]) {
    server.append(message(n));
  }
  open();
  await until(stream, (s) => s.status === "live" && s.seq === 3);
  server.reset([message(7)]);
  server.drop();
  await until(stream, (s) => s.status === "live" && ids(stream).length === 1);
  expect(ids(stream)).toEqual(["msg_7"]);
  expect(stream.snapshot().seq).toBe(1);
});

test("a store told to reset still holds the runs the welcome says are under way", async () => {
  server.append(message(1));
  server.append(message(2));
  open();
  await until(stream, (s) => s.status === "live" && s.seq === 2);
  server.reset([message(7)]);
  server.activeRuns = [{ run_id: "run_9", thread_id: "thr_1" }];
  server.drop();
  await until(stream, (s) => s.status === "live" && ids(stream).length === 1);
  expect(stream.snapshot().state.runs.run_9?.status).toBe("running");
});

test("a reset whose replay is cut short goes on from where the replay got to", async () => {
  for (const n of [1, 2, 3]) {
    server.append(message(n));
  }
  open();
  await until(stream, (s) => s.status === "live" && s.seq === 3);
  server.reset([message(7), message(8)]);
  server.cutNextReplay(1);
  server.drop();
  await server.hello(3);
  await until(stream, (s) => s.status === "live" && s.seq === 2);
  expect(ids(stream)).toEqual(["msg_7", "msg_8"]);
  expect(server.hellos.map((hello) => hello.resume_after_seq)).toEqual([0, 3, 1]);
});

test("a command unanswered when the connection drops is sent again with its id", async () => {
  open();
  await until(stream, (s) => s.status === "live");
  server.answer("drop", { ok: true });
  const settled = await stream.send(
    { type: "post_message", thread_id: "thr_1", content: "Draft the plan" },
    "c_1",
  );
  expect(settled.outcome).toBe("done");
  expect(server.commands).toEqual(["c_1", "c_1"]);
});

test("a create sent again and refused because its id is used was carried out the first time", async () => {
  open();
  await until(stream, (s) => s.status === "live");
  server.answer("drop", { rejection: "invalid_state", reason: "already_exists" });
  const settled = await stream.send(
    { type: "create_thread", thread_id: "thr_9", title: "Retro" },
    "c_2",
  );
  expect(settled).toEqual({ outcome: "done", result: expect.objectContaining({ ok: false }) });
});

test("a create sent again and refused for another reason is a refusal", async () => {
  open();
  await until(stream, (s) => s.status === "live");
  server.answer("drop", { rejection: "invalid_state" });
  const settled = await stream.send(
    { type: "create_thread", thread_id: "thr_9", title: "Retro" },
    "c_4",
  );
  expect(settled.outcome).toBe("refused");
});

test("a refusal the first time is a refusal", async () => {
  open();
  await until(stream, (s) => s.status === "live");
  server.answer({ rejection: "invalid_state" });
  const settled = await stream.send(
    { type: "create_thread", thread_id: "thr_9", title: "Retro" },
    "c_3",
  );
  expect(settled.outcome).toBe("refused");
});

test("a refusal is heard, with the server's answer, and a command carried out isn't", async () => {
  open();
  await until(stream, (s) => s.status === "live");
  const heard: unknown[] = [];
  const stop = stream.onRefused((result) => heard.push(result.rejection?.type));
  server.answer({ ok: true });
  await stream.send({ type: "post_message", thread_id: "thr_1", content: "Hi" }, "c_4");
  server.answer({ rejection: "not_enabled" });
  await stream.send({ type: "create_thread", thread_id: "thr_8", title: "Plan" }, "c_5");
  stop();
  server.answer({ rejection: "forbidden" });
  await stream.send({ type: "create_thread", thread_id: "thr_7", title: "Plan" }, "c_6");
  expect(heard).toEqual(["not_enabled"]);
});

test("closing settles every unanswered command, and refuses new ones", async () => {
  open();
  await until(stream, (s) => s.status === "live");
  server.answer("drop");
  const pending = stream.send({ type: "stop_run", run_id: "run_1" }, "c_4");
  await until(stream, (s) => s.status === "connecting");
  stream.close();
  expect(await pending).toEqual({ outcome: "closed" });
  expect(await stream.send({ type: "stop_run", run_id: "run_1" })).toEqual({ outcome: "closed" });
});

test("an error frame is shown, and the store stays live", async () => {
  open();
  await until(stream, (s) => s.status === "live");
  server.send({ type: "error", message: "not a command frame" });
  const snapshot = await until(stream, (s) => s.error !== null);
  expect(snapshot).toMatchObject({ error: "not a command frame", status: "live" });
});

test("a store the server refuses stops, and doesn't reconnect", async () => {
  open();
  await until(stream, (s) => s.status === "live");
  server.drop(4403);
  await until(stream, (s) => s.status === "closed");
  expect(server.hellos).toHaveLength(1);
});

test("a command unanswered when the server refuses the store for good settles closed, and so does one sent after", async () => {
  open();
  await until(stream, (s) => s.status === "live");
  server.answer("silent");
  const unanswered = stream.send({ type: "stop_run", run_id: "run_1" } as never, "cmd-1");
  await vi.waitFor(() => expect(server.commands).toHaveLength(1));
  server.drop(4401);
  await expect(unanswered).resolves.toEqual({ outcome: "closed" });
  await until(stream, (s) => s.status === "closed");
  await expect(stream.send({ type: "stop_run", run_id: "run_1" } as never)).resolves.toEqual({
    outcome: "closed",
  });
  expect(server.commands).toHaveLength(1);
});

test("after the server refuses the token, a reconnect with a fresh one goes live", async () => {
  let token = "old";
  stream = new Stream(artifactr, { url: () => `${server.url}?access_token=${token}` });
  stream.open();
  await until(stream, (s) => s.status === "live");
  server.drop(4401);
  await until(stream, (s) => s.status === "closed");
  token = "new";
  stream.reconnect();
  await server.hello(2);
  await until(stream, (s) => s.status === "live");
});

test("a reconnect during the backoff connects at once, and only once", async () => {
  server.append(message(1));
  open();
  await until(stream, (s) => s.status === "live" && s.seq === 1);
  server.drop();
  await until(stream, (s) => s.status === "connecting");
  stream.reconnect();
  await server.hello(2);
  await until(stream, (s) => s.status === "live");
  await new Promise((resolve) => setTimeout(resolve, 200)); // past any backoff left behind
  expect(server.hellos.map((hello) => hello.resume_after_seq)).toEqual([0, 1]);
});

test("reconnect works handed on detached, as a page gives it to a button, and connects anew", async () => {
  const store = open();
  await until(store, (snapshot) => snapshot.status === "live");
  server.drop(4403); // a close the store never reconnects from by itself
  await until(store, (snapshot) => snapshot.status === "closed");
  const { reconnect } = store;
  reconnect();
  await until(store, (snapshot) => snapshot.status === "live");
});

/** A WebSocket that does what the test says, on the timers the test controls. */
class FakeSocket {
  static all: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;
  onclose: ((closed: { code: number }) => void) | null = null;
  constructor() {
    FakeSocket.all.push(this);
  }
  send() {}
  close() {}
  /** Connected and caught up, as a server that then drops it does. */
  caughtUp() {
    this.onopen?.();
    const say = (frame: object) => this.onmessage?.({ data: JSON.stringify(frame) });
    say({
      type: "welcome",
      protocol: "artifactr.v1",
      workspace_id: "w",
      head_seq: 0,
      reset: false,
    });
    say({ type: "replay_complete", up_to_seq: 0 });
  }
  /** Dropped by the server with `code`. */
  drop(code: number) {
    this.onclose?.({ code });
  }
}

const last = () => {
  const socket = FakeSocket.all.at(-1);
  if (!socket) {
    throw new Error("no socket");
  }
  return socket;
};

/** Milliseconds from a drop until the next connection, found by stepping the clock. */
function waitForNext(): number {
  const before = FakeSocket.all.length;
  let waited = 0;
  while (FakeSocket.all.length === before && waited < 60_000) {
    vi.advanceTimersByTime(50);
    waited += 50;
  }
  return waited;
}

/** A store on a fake clock and fake sockets, with `Math.random` fixed at `random`. */
function onFakes(random: number) {
  vi.useFakeTimers();
  vi.spyOn(Math, "random").mockReturnValue(random);
  vi.stubGlobal("WebSocket", FakeSocket);
  FakeSocket.all = [];
  stream = new Stream(artifactr, { url: () => "ws://x" });
  stream.open();
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test.each([
  [1, [100, 500, 1000, 2000, 5000, 5000]],
  [0, [50, 250, 500, 1000, 2500, 2500]],
])(
  "a connection dropped the moment it is caught up backs off, not in a loop (random %d)",
  (random, expected) => {
    onFakes(random);
    const waits: number[] = [];
    for (let n = 0; n < 6; n++) {
      last().caughtUp();
      last().drop(4429);
      waits.push(waitForNext());
    }
    expect(waits).toEqual(expected);
    // One that stays live for a while is a fresh start.
    last().caughtUp();
    vi.advanceTimersByTime(10_000);
    last().drop(1006);
    expect(waitForNext()).toBe(random === 1 ? 100 : 50);
  },
);

test.each([4400, 4401, 4403])("a drop with %d is not retried, and leaves no timer", (code) => {
  onFakes(1);
  last().caughtUp();
  last().drop(code);
  expect(stream.snapshot().status).toBe("closed");
  expect(vi.getTimerCount()).toBe(0);
  vi.advanceTimersByTime(60_000);
  expect(FakeSocket.all).toHaveLength(1);
});

test("close() leaves no timer behind, mid-backoff or live", () => {
  onFakes(1);
  last().caughtUp();
  stream.close();
  expect(vi.getTimerCount()).toBe(0);
  onFakes(1);
  last().drop(1006); // waiting to reconnect
  stream.close();
  expect(vi.getTimerCount()).toBe(0);
  vi.advanceTimersByTime(60_000);
  expect(FakeSocket.all).toHaveLength(1);
});

test("reconnect() mid-backoff connects once, starts the backoff over, and leaves one timer", () => {
  onFakes(1);
  for (let n = 0; n < 3; n++) {
    last().drop(1006);
    waitForNext();
  }
  last().drop(1006); // the fourth wait would be 2000
  const before = FakeSocket.all.length;
  stream.reconnect();
  expect(FakeSocket.all).toHaveLength(before + 1);
  expect(vi.getTimerCount()).toBe(0);
  last().drop(1006);
  expect(waitForNext()).toBe(100);
  expect(FakeSocket.all).toHaveLength(before + 2);
});

const delta = (text: string) => ({
  type: "live",
  run_id: "run_1",
  event: { type: "text_delta", part: 0, delta: text },
});

test("a run's frames are taken at once and heard once a frame later, and a welcome starts its live output over", async () => {
  server.append({ type: "run_started", run_id: "run_1", thread_id: "thr_1" });
  open();
  await until(stream, (s) => s.status === "live");
  let heard = 0;
  stream.subscribe(() => {
    heard += 1;
  });
  server.send({
    type: "live",
    run_id: "run_1",
    event: { type: "part_started", part: 0, part_kind: "text" },
  });
  server.send(delta("Hel"));
  server.send(delta("lo"));
  await until(stream, (s) => s.state.runs.run_1?.text === "Hello");
  expect(heard).toBe(1);
  // The connection drops: the server welcomes it again and replays the run's frames.
  server.drop();
  await server.hello(2); // welcomed again: the frames come after the welcome
  server.send(delta("Hel"));
  server.send(delta("lo"));
  await until(stream, (s) => s.status === "live" && s.state.runs.run_1?.text === "Hello");
  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(stream.snapshot().state.runs.run_1?.text).toBe("Hello");
});

test("with the browser's frames, a run's frames are heard as the next is drawn, not before", async () => {
  const drawn: FrameRequestCallback[] = [];
  vi.stubGlobal("requestAnimationFrame", (fn: FrameRequestCallback) => drawn.push(fn));
  vi.stubGlobal("cancelAnimationFrame", () => {});
  server.append({ type: "run_started", run_id: "run_1", thread_id: "thr_1" });
  open();
  await until(stream, (s) => s.status === "live");
  let heard = 0;
  stream.subscribe(() => {
    heard += 1;
  });
  server.send(delta("He"));
  server.send(delta("llo"));
  await new Promise((resolve) => setTimeout(resolve, 40));
  expect(stream.snapshot().state.runs.run_1?.text).toBe("Hello"); // taken at once
  expect(heard).toBe(0); // told once a frame is drawn
  expect(drawn).toHaveLength(1);
  drawn[0]?.(0);
  expect(heard).toBe(1);
});

test("a hidden tab, which draws no frames, still hears a run's frames a moment later", async () => {
  vi.stubGlobal("requestAnimationFrame", () => 1); // never drawn
  vi.stubGlobal("cancelAnimationFrame", () => {});
  server.append({ type: "run_started", run_id: "run_1", thread_id: "thr_1" });
  open();
  await until(stream, (s) => s.status === "live");
  let heard = 0;
  stream.subscribe(() => {
    heard += 1;
  });
  server.send(delta("Hi"));
  await new Promise((resolve) => setTimeout(resolve, 250));
  expect(heard).toBe(1);
});
