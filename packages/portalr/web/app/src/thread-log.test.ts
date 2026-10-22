import type { Artifactr } from "@portalr/client";
import { expect, test } from "vitest";
import { retryOf } from "./thread-log";

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
  expect(retryOf(both, two, "alice")?.content).toBe("Posted as m1\n\nPosted as m2");
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

test("a thread whose every try id is someone else's offers no try, rather than looking for ever", () => {
  const taken = Array.from({ length: 100 }, (_, at) =>
    message(at === 0 ? "msg_again_run_1" : `msg_again_run_1_${at + 1}`, "mallory"),
  );
  expect(retryOf(thread(message("m1", "alice"), ...taken), { run_1: run({}) }, "alice")).toBeNull();
  // One short of that, the last id is still offered.
  expect(
    retryOf(thread(message("m1", "alice"), ...taken.slice(0, 99)), { run_1: run({}) }, "alice")?.id,
  ).toBe("msg_again_run_1_100");
});
