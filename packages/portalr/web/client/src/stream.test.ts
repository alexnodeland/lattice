import { afterEach, beforeEach, expect, test } from "vitest";
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
  server.answer("drop", { rejection: "invalid_state" });
  const settled = await stream.send(
    { type: "create_thread", thread_id: "thr_9", title: "Retro" },
    "c_2",
  );
  expect(settled).toEqual({ outcome: "done", result: expect.objectContaining({ ok: false }) });
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
