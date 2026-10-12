import { afterEach, beforeEach, expect, test } from "vitest";
import { artifactr, type Workspace } from "./artifactr";
import type * as v1 from "./generated/artifactr.v1";
import { type Settled, Stream } from "./stream";
import { ScriptedServer } from "./test/server";
import { until } from "./test/until";

type ThreadStream = Stream<Workspace, v1.Server, v1.Command, v1.CommandResult>;

let server: ScriptedServer;
let stream: ThreadStream;

beforeEach(() => {
  server = new ScriptedServer();
});

afterEach(() => {
  stream?.close();
  server.stop();
});

function open(after = 0): ThreadStream {
  stream = new Stream(artifactr, { url: server.url, after });
  stream.open();
  return stream;
}

/** Every `seq` the store applies, in the order it applies them. */
function applied(store: ThreadStream): number[] {
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

test("a store replays the log, then goes live", async () => {
  server.append({ type: "thread_created", thread_id: "thr_1", title: "Launch" });
  server.append(message(1));
  open();
  await until(stream, (s) => s.status === "live");
  server.append(message(2));
  const { state, seq } = await until(stream, (s) => s.seq === 3);
  expect(seq).toBe(3);
  expect(state.threads.thr_1?.title).toBe("Launch");
  expect(state.threads.thr_1?.messages.map((m) => m.id)).toEqual(["msg_1", "msg_2"]);
  expect(server.hellos).toEqual([
    expect.objectContaining({ protocol: "artifactr.v1", resume_after_seq: 0 }),
  ]);
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
  const { state } = await until(stream, (s) => s.seq === 6);
  expect(seqs).toEqual([1, 2, 3, 4, 5, 6]);
  expect(state.threads.thr_1?.messages.map((m) => m.id)).toEqual(
    [1, 2, 3, 4, 5, 6].map((n) => `msg_${n}`),
  );
  expect(server.hellos.map((hello) => hello.resume_after_seq)).toEqual([0, 3]);
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
      } as v1.EventFrame),
    artifactr.initial(),
  );
  stream = new Stream(artifactr, { url: server.url, after: 2 }, tail);
  stream.open();
  const { state } = await until(stream, (s) => s.status === "live" && s.seq === 3);
  expect(state.threads.thr_1?.messages.map((m) => m.id)).toEqual(["msg_1", "msg_2", "msg_3"]);
  expect(server.hellos[0]?.resume_after_seq).toBe(2);
});

test("a store told to reset discards what it holds and rebuilds from the replay", async () => {
  for (const n of [1, 2, 3]) {
    server.append(message(n));
  }
  open();
  await until(stream, (s) => s.status === "live" && s.seq === 3);
  server.reset([message(7)]);
  server.drop();
  const { state } = await until(
    stream,
    (s) => s.status === "live" && s.state.threads.thr_1?.messages.length === 1,
  );
  expect(state.threads.thr_1?.messages.map((m) => m.id)).toEqual(["msg_7"]);
  expect(stream.snapshot().seq).toBe(1);
});

test("a command unanswered when the connection drops is sent again with its id", async () => {
  open();
  await until(stream, (s) => s.status === "live");
  server.answer("drop", { ok: true });
  const settled = await stream.send(
    { type: "post_message", thread_id: "thr_1", content: "Draft the plan" },
    "c_1",
  );
  expect(settled.done).toBe(true);
  expect(server.commands).toEqual(["c_1", "c_1"]);
});

test("a create sent again and refused because its id is used was carried out the first time", async () => {
  open();
  await until(stream, (s) => s.status === "live");
  server.answer("drop", { rejection: "invalid_state" });
  const create: v1.Command = { type: "create_thread", thread_id: "thr_9", title: "Retro" };
  const settled: Settled<v1.CommandResult> = await stream.send(create, "c_2");
  expect(settled).toEqual({ done: true, result: expect.objectContaining({ ok: false }) });
});

test("a refusal the first time is a refusal", async () => {
  open();
  await until(stream, (s) => s.status === "live");
  server.answer({ rejection: "invalid_state" });
  const settled = await stream.send(
    { type: "create_thread", thread_id: "thr_9", title: "Retro" },
    "c_3",
  );
  expect(settled.done).toBe(false);
});

test("a store the server refuses stops, and doesn't reconnect", async () => {
  open();
  await until(stream, (s) => s.status === "live");
  server.drop(4403);
  await until(stream, (s) => s.status === "closed");
  expect(server.hellos).toHaveLength(1);
});

test("a reconnect resumes on a new connection", async () => {
  server.append(message(1));
  open();
  await until(stream, (s) => s.status === "live" && s.seq === 1);
  stream.reconnect();
  await until(stream, () => server.hellos.length === 2);
  await until(stream, (s) => s.status === "live");
  expect(server.hellos.map((hello) => hello.resume_after_seq)).toEqual([0, 1]);
});
