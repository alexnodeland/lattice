import type { Reflexr } from "@portalr/client";
import { expect, test } from "vitest";
import { actorName, commandFor, listed, offered, refusedAs, shownOf } from "./runs";

const run = (id: string, status: Reflexr.Run["status"], started: number): Reflexr.Run => ({
  id,
  rule: "ops:page",
  status,
  attempt: 1,
  retries: 0,
  started,
  reason: null,
  history: [],
  feedback: [],
});

const RUNS = Object.fromEntries(
  (
    [
      "pending",
      "running",
      "retrying",
      "succeeded",
      "dead_lettered",
      "cancelled",
      "skipped",
    ] as const
  ).map((status, at) => [status, run(status, status, at + 1)]),
);

test("an address keeps a workspace's name and a list it offers, and defaults the rest", () => {
  expect(shownOf({})).toEqual({ workspace: undefined, show: "attention" });
  expect(shownOf({ workspace: "notes", show: "all" })).toEqual({ workspace: "notes", show: "all" });
  expect(shownOf({ workspace: "100%/a b", show: "every" })).toEqual({
    workspace: "100%/a b",
    show: "attention",
  });
  expect(shownOf({ workspace: "" }).workspace).toBeUndefined();
  expect(shownOf({ workspace: "x".repeat(257) }).workspace).toBeUndefined();
  expect(shownOf({ workspace: "a\0b" }).workspace).toBeUndefined();
  expect(shownOf({ workspace: 42 }).workspace).toBeUndefined();
});

test("runs needing attention are the dead-lettered and the retrying, newest first", () => {
  expect(listed(RUNS, "attention").map((each) => each.id)).toEqual(["dead_lettered", "retrying"]);
  expect(listed(RUNS, "all").map((each) => each.id)).toEqual([
    "skipped",
    "cancelled",
    "dead_lettered",
    "succeeded",
    "retrying",
    "running",
    "pending",
  ]);
});

test("each state offers what reflexr takes in it, where grantr allows", () => {
  const all = new Set(["reflexr:retry_run", "reflexr:skip_run", "reflexr:cancel_run"]);
  expect(offered("dead_lettered", all)).toEqual(["retry", "skip", "cancel"]);
  expect(offered("retrying", all)).toEqual(["retry", "skip", "cancel"]);
  expect(offered("pending", all)).toEqual(["skip", "cancel"]);
  expect(offered("running", all)).toEqual(["cancel"]);
  expect(offered("cancelled", all)).toEqual(["retry"]);
  expect(offered("skipped", all)).toEqual(["retry"]);
  expect(offered("succeeded", all)).toEqual([]);
  expect(offered("dead_lettered", new Set(["reflexr:skip_run"]))).toEqual(["skip"]);
  expect(offered("dead_lettered", new Set())).toEqual([]);
});

test("a command carries the reason only if one was given, and never a retry's", () => {
  expect(commandFor("retry", "r1", "ignored")).toEqual({ type: "retry_run", run_id: "r1" });
  expect(commandFor("skip", "r1", "known issue")).toEqual({
    type: "skip_run",
    run_id: "r1",
    reason: "known issue",
  });
  expect(commandFor("cancel", "r1", "")).toEqual({ type: "cancel_run", run_id: "r1" });
});

test("an actor is its name, else its id, else what it is", () => {
  expect(actorName({ kind: "user", id: "alice", name: "Alice" })).toBe("Alice");
  expect(actorName({ kind: "user", id: "alice" })).toBe("alice");
  expect(actorName({ kind: "system", name: "reflexr" } as Reflexr.Intervention["actor"])).toBe(
    "reflexr",
  );
});

test("a refusal is said in words, whatever the server's own", () => {
  expect(refusedAs({ type: "forbidden" })).toMatch(/aren't allowed/);
  expect(refusedAs({ type: "not_found" })).toMatch(/no longer exists/);
  expect(refusedAs({ type: "invalid_state" })).toMatch(/has changed/);
  expect(refusedAs({ type: "validation", message: "text cannot hold a NUL character" })).toBe(
    "text cannot hold a NUL character",
  );
  expect(refusedAs({ type: "odd" })).toBe("The server refused it.");
  expect(refusedAs(null)).toBe("The server refused it.");
});
