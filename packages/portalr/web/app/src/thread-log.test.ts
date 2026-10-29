import type { Artifactr } from "@portalr/client";
import { expect, test } from "vitest";
import { retryOf, threadLog } from "./thread-log";

const message = (id: string, by: string): Artifactr.Message => ({
  id,
  seq: 1,
  actor: { kind: "user", id: by },
  content: `Posted as ${id}`,
  kind: "message",
  runId: null,
  feedback: [],
});

const run = (change: Partial<Artifactr.Run>): Artifactr.Run => ({
  id: "run_1",
  threadId: "thr_1",
  status: "failed",
  tools: {},
  text: "",
  live: {
    phase: "starting",
    tool: null,
    calls: 0,
    argsChars: 0,
    thinking: "",
    thoughtMs: 0,
    outputChars: 0,
    since: 0,
    at: 0,
    part: null,
    reply: "pending",
    truncated: false,
    framed: false,
    usage: null,
  },
  requests: [],
  answered: [],
  started: 2,
  ended: 3,
  error: null,
  reason: null,
  prompt: ["m1"],
  actsFor: "alice",
  questions: [],
  feedback: [],
  ...change,
});

const thread = (...messages: Artifactr.Message[]): Artifactr.Thread => ({
  id: "thr_1",
  title: "",
  mode: "edit",
  focus: [],
  messages,
  active: 1,
  activeAt: null,
});

test("a failed turn is tried again with the message that started it, under the run's own id", () => {
  const runs = { run_1: run({}) };
  expect(retryOf(thread(message("m1", "alice")), runs, "alice")).toEqual({
    run: "run_1",
    id: "msg_again_run_1",
    content: "Posted as m1",
  });
  const two = { run_1: run({ prompt: ["m1", "m2"] }) };
  const both = thread(message("m1", "alice"), message("m2", "alice"));
  expect(retryOf(both, two, "alice")).toMatchObject({ content: "Posted as m1\n\nPosted as m2" });
});

test("it isn't tried again by others, twice, or when the thread's latest turn didn't fail", () => {
  const failed = { run_1: run({}) };
  expect(retryOf(thread(message("m1", "bob")), failed, "alice")).toBeNull();
  const tried = { ...message("msg_again_run_1", "alice"), content: "Posted as m1" };
  expect(retryOf(thread(message("m1", "alice"), tried), failed, "alice")).toBeNull();
  const later = { ...failed, run_2: run({ id: "run_2", status: "completed", started: 9 }) };
  expect(retryOf(thread(message("m1", "alice")), later, "alice")).toBeNull();
  expect(
    retryOf(thread(message("m1", "alice")), { run_1: run({ prompt: [] }) }, "alice"),
  ).toBeNull();
});

test("an id someone else took first doesn't stop the try: the next is used", () => {
  const squatted = thread(message("m1", "alice"), message("msg_again_run_1", "mallory"));
  expect(retryOf(squatted, { run_1: run({}) }, "alice")?.id).toBe("msg_again_run_1_2");
  const tried = { ...message("msg_again_run_1_2", "alice"), content: "Posted as m1" };
  const after = thread(message("m1", "alice"), message("msg_again_run_1", "mallory"), tried);
  expect(retryOf(after, { run_1: run({}) }, "alice")).toBeNull();
});

test("a thread whose every try id is someone else's says it can't try, rather than looking for ever", () => {
  const taken = Array.from({ length: 100 }, (_, at) =>
    message(at === 0 ? "msg_again_run_1" : `msg_again_run_1_${at + 1}`, "mallory"),
  );
  expect(retryOf(thread(message("m1", "alice"), ...taken), { run_1: run({}) }, "alice")).toEqual({
    run: "run_1",
    id: null,
  });
  // One short of that, the last id is still offered.
  expect(
    retryOf(thread(message("m1", "alice"), ...taken.slice(0, 99)), { run_1: run({}) }, "alice")?.id,
  ).toBe("msg_again_run_1_100");
});

test("a turn that failed, or was stopped, shows what it had streamed before why, where it ended", () => {
  const failed = run({ text: "Half a rep", ended: 3 });
  const stopped = run({
    id: "run_2",
    status: "stopped",
    started: 4,
    ended: 5,
    text: "",
    live: { ...failed.live, thinking: "Hmm" },
  });
  const quiet = run({ id: "run_3", status: "completed", started: 6, ended: 7 });
  const bare = run({ id: "run_4", status: "stopped", started: 8, ended: 9 });
  const kinds = threadLog(thread(message("m1", "alice")), {
    run_1: failed,
    run_2: stopped,
    run_3: quiet,
    run_4: bare,
  }).map((entry) => `${entry.kind}@${entry.seq}`);
  // A stop is shown even where nothing had streamed; a failure with nothing streamed isn't.
  expect(kinds).toEqual(["message@1", "partial@3", "failed@3", "partial@5", "partial@9"]);
});

const decided = (id: string, runId: string | null): Artifactr.Proposal => ({
  id,
  threadId: "thr_1",
  runId,
  change: null,
  rationale: null,
  status: "accept",
});

test("a decided proposal is a line after the last entry of the run that made it, and the thread's last where none did", () => {
  const tools = (seq: number) => ({
    t1: {
      name: "read_artifact",
      status: "ok",
      args: "{}",
      result: "",
      argsCut: false,
      resultCut: false,
      seq,
    },
  });
  const first = run({ id: "run_1", status: "completed", started: 2, ended: 4, tools: tools(3) });
  const second = run({ id: "run_2", status: "completed", started: 5, ended: 7, tools: tools(6) });
  const log = threadLog(
    { ...thread(message("m1", "alice")), messages: [message("m1", "alice")] },
    { run_1: first, run_2: second },
    [],
    {},
    [decided("p_second", "run_2"), decided("p_first", "run_1"), decided("p_person", null)],
  );
  const order = log.map((entry) => (entry.kind === "proposal" ? entry.proposal.id : entry.kind));
  // Each follows its run's last entry, which is its call: half a place on; a person's is last.
  expect(order).toEqual(["message", "tools", "p_first", "tools", "p_second", "p_person"]);
});

test("a run's later entries keep the proposal behind them: it moves on as the run does", () => {
  const tool = {
    name: "read_artifact",
    status: "ok",
    args: "{}",
    result: "",
    argsCut: false,
    resultCut: false,
  };
  const going = run({
    status: "running",
    ended: null,
    tools: { t1: { ...tool, seq: 3 }, t2: { ...tool, seq: 9 } },
  });
  const order = threadLog(thread(message("m1", "alice")), { run_1: going }, [], {}, [
    decided("p_1", "run_1"),
  ]).map((entry) => (entry.kind === "proposal" ? entry.proposal.id : entry.kind));
  expect(order.at(-1)).toBe("p_1");
});
