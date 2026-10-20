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
});

test("a failed turn is tried again with the message that started it, under the run's own id", () => {
  const runs = { run_1: run({}) };
  expect(retryOf(thread(message("m1", "alice")), runs, "alice")).toEqual({
    id: "msg_again_run_1",
    content: "Posted as m1",
  });
});

test("it isn't tried again by others, twice, or when the thread's latest turn didn't fail", () => {
  const failed = { run_1: run({}) };
  expect(retryOf(thread(message("m1", "bob")), failed, "alice")).toBeNull();
  const again = thread(message("m1", "alice"), message("msg_again_run_1", "alice"));
  expect(retryOf(again, failed, "alice")).toBeNull();
  const later = { ...failed, run_2: run({ id: "run_2", status: "completed", started: 9 }) };
  expect(retryOf(thread(message("m1", "alice")), later, "alice")).toBeNull();
  expect(
    retryOf(thread(message("m1", "alice")), { run_1: run({ prompt: [] }) }, "alice"),
  ).toBeNull();
});
