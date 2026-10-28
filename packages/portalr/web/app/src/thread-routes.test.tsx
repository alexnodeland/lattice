/**
 * A thread as a route, over a replayed artifactr log: the reader's messages at the end of the line
 * and the agent's at its start, each run's tool calls and questions where the log has them, and a
 * failed turn that says why and is tried again, the message it sends shown at once.
 */

import { afterEach, expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { open, type Serve } from "./test/app";

const ALICE = { kind: "user", id: "alice" };
const agent = (run: string) => ({
  kind: "agent",
  thread_id: "thr_1",
  run_id: run,
  on_behalf_of: ALICE,
});

const QUESTIONS = {
  questions: [
    {
      question: "Which week?",
      header: "Week",
      options: [{ label: "This week" }, { label: "The next", recommended: true }],
    },
  ],
};

/** The log, each event at its place, by whom. */
const LOG = (
  [
    [ALICE, { type: "thread_created", thread_id: "thr_1", title: "Launch" }],
    [ALICE, { type: "message_posted", thread_id: "thr_1", message_id: "m1", content: "Plan it" }],
    [agent("run_1"), { type: "run_started", run_id: "run_1", thread_id: "thr_1" }],
    [
      agent("run_1"),
      {
        type: "tool_called",
        run_id: "run_1",
        thread_id: "thr_1",
        tool_call_id: "t1",
        tool_name: "create_artifact",
        args_summary: '{"kind": "note"}',
      },
    ],
    [
      agent("run_1"),
      {
        type: "tool_returned",
        run_id: "run_1",
        thread_id: "thr_1",
        tool_call_id: "t1",
        tool_name: "create_artifact",
        status: "ok",
        summary: "Done: note_1 is now at version 1.",
      },
    ],
    [
      agent("run_1"),
      {
        type: "run_paused",
        run_id: "run_1",
        thread_id: "thr_1",
        requests: [
          { kind: "question", tool_call_id: "q1", tool_name: "ask_user", args: QUESTIONS },
        ],
      },
    ],
    [
      ALICE,
      {
        type: "deferred_answered",
        run_id: "run_1",
        thread_id: "thr_1",
        tool_call_id: "q1",
        tool_name: "ask_user",
        answer: { answers: [{ selected: ["The next"] }] },
      },
    ],
    [
      agent("run_1"),
      {
        type: "message_posted",
        thread_id: "thr_1",
        message_id: "m2",
        content: "Planned for next week.",
        run_id: "run_1",
      },
    ],
    [
      agent("run_1"),
      { type: "run_ended", run_id: "run_1", thread_id: "thr_1", status: "completed" },
    ],
    [
      ALICE,
      { type: "message_posted", thread_id: "thr_1", message_id: "m3", content: "Draft a rule" },
    ],
    [
      agent("run_2"),
      { type: "run_started", run_id: "run_2", thread_id: "thr_1", message_ids: ["m3"] },
    ],
    [
      agent("run_2"),
      {
        type: "tool_returned",
        run_id: "run_2",
        thread_id: "thr_1",
        tool_call_id: "t2",
        tool_name: "draft_rule",
        status: "retry",
        summary: "rule\n  Field required",
      },
    ],
    [
      agent("run_2"),
      {
        type: "run_ended",
        run_id: "run_2",
        thread_id: "thr_1",
        status: "failed",
        error: "Tool 'draft_rule' exceeded max retries count of 1",
        reason: "tool_retries_exhausted",
      },
    ],
  ] as const
).map(([actor, event], index) => ({
  type: "event",
  seq: index + 1,
  id: `evt_${index + 1}`,
  ts: "2026-10-20T00:00:00Z",
  workspace_id: "notes",
  actor,
  event,
}));

const serve: Serve = async (request, path) => {
  if (path === "/grantr/v1/checks") {
    const asked: unknown[] = await request.json();
    return Response.json(asked.map(() => true));
  }
  return path.startsWith("/grantr/v1/tenants/acme/") ? Response.json([]) : undefined;
};

afterEach(() => {
  vi.unstubAllGlobals();
});

test("a thread shows its messages, the reader's on the wash, its calls and questions in place, and why a turn failed", async () => {
  const sent: { type: string; content?: string; message_id?: string }[] = [];
  const { screen } = await open(
    "/t/acme/w/notes/threads/thr_1",
    serve,
    (command) => {
      sent.push(command);
      return null;
    },
    { artifactrLog: LOG },
  );
  const log = screen.getByRole("log", { name: "Messages" });
  await expect.element(log.getByText("Planned for next week.")).toBeVisible();
  const [mine, theirs] = [
    log.getByRole("listitem", { name: "You" }).first().element(),
    log.getByRole("listitem", { name: "Assistant" }).element(),
  ];
  // The reader's words on the quiet wash at the end of the line, the agent's unboxed at its start.
  expect(getComputedStyle(mine).alignSelf).toBe("flex-end");
  expect(getComputedStyle(theirs).alignSelf).toBe("flex-start");
  const words = (item: Element) => getComputedStyle(item.querySelector(":scope > div") as Element);
  expect(words(mine).backgroundColor).not.toBe("rgba(0, 0, 0, 0)");
  expect(words(theirs).backgroundColor).toBe("rgba(0, 0, 0, 0)");
  // Each run's calls a quiet line, in plain words, a refusal marked.
  const created = log.getByRole("button", { name: "Made an artifact: 1 tool call" }).element();
  await expect
    .element(log.getByRole("button", { name: "Drafted a rule · 1 failed: 1 tool call" }))
    .toBeVisible();
  const asked = log.getByRole("region", { name: "The agent asked" });
  await expect.element(asked.getByText("The next")).toBeVisible();
  await expect.element(asked.getByText("Answered by You")).toBeVisible();
  // In the log's order: the call, then the question, then the agent's answer.
  const order = (element: Element, other: Element) =>
    element.compareDocumentPosition(other) & Node.DOCUMENT_POSITION_FOLLOWING;
  expect(order(created as Element, asked.element())).toBeTruthy();
  expect(order(asked.element(), theirs)).toBeTruthy();
  const failed = log.getByRole("alert");
  await expect.element(failed.getByText(/The model kept calling a tool/)).toBeVisible();
  await failed.getByRole("button", { name: "Try again" }).click();
  await expect.element(failed.getByText("Details")).toBeVisible(); // the turn acted for alice
  expect(sent.at(-1)).toMatchObject({
    type: "post_message",
    content: "Draft a rule",
    message_id: "msg_again_run_2",
  });
  const posting = log.getByRole("listitem", { name: "You" }).last();
  await expect.element(posting.getByText("Draft a rule")).toBeVisible();
  await expect.element(posting.getByText("Sending…")).toBeVisible();
});

test("a message posted shows at once, and goes if the server refuses it", async () => {
  const { screen } = await open(
    "/t/acme/w/notes/threads/thr_1",
    serve,
    (command) => (command.type === "post_message" ? "forbidden" : null),
    { artifactrLog: LOG.slice(0, 2) },
  );
  const log = screen.getByRole("log", { name: "Messages" });
  await expect.element(log.getByText("Plan it")).toBeVisible();
  await screen.getByRole("textbox", { name: "Message" }).fill("Hello?");
  await screen.getByRole("button", { name: "Send" }).click();
  await expect.element(screen.getByText("That wasn't done: the server refused it.")).toBeVisible();
  expect(log.getByText("Hello?").elements()).toHaveLength(0);
  await expect.element(screen.getByRole("textbox", { name: "Message" })).toHaveValue("Hello?");
});

test("Try again refused as already posted, by another tab, says nothing went wrong", async () => {
  const { screen } = await open(
    "/t/acme/w/notes/threads/thr_1",
    serve,
    (command) =>
      command.type === "post_message"
        ? {
            type: "invalid_state",
            message: "message msg_again_run_2 already exists",
            reason: "already_exists",
            entity: "message",
            id: "msg_again_run_2",
          }
        : null,
    { artifactrLog: LOG },
  );
  const log = screen.getByRole("log", { name: "Messages" });
  await log.getByRole("button", { name: "Try again" }).click();
  const posting = log.getByRole("listitem", { name: "You" }).last();
  await expect.element(posting.getByText("Sending…")).toBeVisible();
  expect(screen.getByText("That wasn't done: the server refused it.").elements()).toHaveLength(0);
});

test("a thread's page is marked in Threads, its way back up, with no breadcrumb", async () => {
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, {
    artifactrLog: LOG,
  });
  const threads = screen
    .getByRole("navigation", { name: "Workspace" })
    .first()
    .getByRole("link", { name: "Threads" });
  await expect.element(threads).toHaveAttribute("aria-current", "true");
  expect(screen.getByRole("navigation", { name: "Breadcrumb" }).elements()).toHaveLength(0);
});

test("Try again refused in words alone, without the typed reason, is a refusal", async () => {
  const { screen } = await open(
    "/t/acme/w/notes/threads/thr_1",
    serve,
    (command) =>
      command.type === "post_message"
        ? {
            type: "invalid_state",
            message: "message msg_again_run_2 already exists",
          }
        : null,
    { artifactrLog: LOG },
  );
  const log = screen.getByRole("log", { name: "Messages" });
  await log.getByRole("button", { name: "Try again" }).click();
  await expect.element(screen.getByText("That wasn't done: the server refused it.")).toBeVisible();
});

test("following a thread's link from the list lands on the thread's heading, and Back on the list's", async () => {
  const { screen, router } = await open("/t/acme/w/notes", serve, () => null, {
    artifactrLog: LOG,
  });
  const link = screen
    .getByRole("main")
    .getByRole("link", { name: /Launch/ })
    .first();
  await expect.element(link).toBeVisible();
  (link.element() as HTMLElement).focus();
  await userEvent.keyboard("{Enter}");
  const thread = screen.getByRole("heading", { level: 1 });
  await expect.element(thread).not.toHaveTextContent("Threads");
  await expect.element(thread).toHaveFocus();
  router.history.back();
  await expect.element(screen.getByRole("heading", { level: 1, name: "Threads" })).toHaveFocus();
});

test("a question waiting when the thread is opened leaves the focus be, and is reached by Go to the question", async () => {
  const waiting = LOG.slice(
    0,
    LOG.findIndex((entry) => entry.event.type === "deferred_answered"),
  );
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, {
    artifactrLog: waiting,
  });
  const question = screen.getByRole("radio", { name: "This week" });
  await expect.element(question).toBeVisible();
  await new Promise((settled) => requestAnimationFrame(() => requestAnimationFrame(settled)));
  expect(document.activeElement?.getAttribute("role")).not.toBe("radio");
  await screen.getByRole("button", { name: "Go to the question" }).click();
  // To the question's own named part, inside the request.
  expect(document.activeElement?.closest("#request-q1")).not.toBeNull();
  expect(document.activeElement?.getAttribute("aria-label")).toBe("The agent asks");
  await userEvent.tab();
  expect(document.activeElement?.closest("#request-q1")).not.toBeNull();
});

test("opened at a request, as from Needs you, the page goes to it once the thread is shown", async () => {
  const waiting = LOG.slice(
    0,
    LOG.findIndex((entry) => entry.event.type === "deferred_answered"),
  );
  const { screen } = await open("/t/acme/w/notes/threads/thr_1#request-q1", serve, () => null, {
    artifactrLog: waiting,
  });
  await expect.element(screen.getByRole("radio", { name: "This week" })).toBeVisible();
  await expect.poll(() => document.activeElement?.closest("#request-q1")).not.toBeNull();
  expect(document.activeElement?.getAttribute("aria-label")).toBe("The agent asks");
});

test("another thread's question waiting when its page opens leaves the focus be too", async () => {
  const waiting = LOG.slice(
    0,
    LOG.findIndex((entry) => entry.event.type === "deferred_answered"),
  );
  const second = [
    { type: "thread_created", thread_id: "thr_2", title: "Venue" },
    { type: "run_started", run_id: "run_9", thread_id: "thr_2" },
    {
      type: "run_paused",
      run_id: "run_9",
      thread_id: "thr_2",
      requests: [{ kind: "question", tool_call_id: "q9", tool_name: "ask_user", args: QUESTIONS }],
    },
  ].map((event, at) => ({
    type: "event",
    seq: waiting.length + at + 1,
    id: `evt_t2_${at}`,
    ts: "2026-10-20T00:00:00Z",
    workspace_id: "notes",
    actor: at === 0 ? ALICE : agent("run_9"),
    event,
  }));
  const { screen, router } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, {
    artifactrLog: [...waiting, ...second],
  });
  await expect.element(screen.getByRole("heading", { level: 1, name: "Launch" })).toBeVisible();
  await router.navigate({
    to: "/t/$tenant/w/$workspace/threads/$thread",
    params: { tenant: "acme", workspace: "notes", thread: "thr_2" },
  });
  await expect.element(screen.getByRole("heading", { level: 1, name: "Venue" })).toBeVisible();
  await new Promise((settled) => requestAnimationFrame(() => requestAnimationFrame(settled)));
  expect(document.activeElement?.getAttribute("role")).not.toBe("radio");
});

test("Go to the question reaches a form the agent asks by its name too", async () => {
  const waiting = LOG.slice(0, 3);
  const paused = {
    type: "event",
    seq: waiting.length + 1,
    id: "evt_form",
    ts: "2026-10-20T00:00:00Z",
    workspace_id: "notes",
    actor: agent("run_1"),
    event: {
      type: "run_paused",
      run_id: "run_1",
      thread_id: "thr_1",
      requests: [
        {
          kind: "question",
          tool_call_id: "f1",
          tool_name: "ask_form",
          args: {
            title: "Dietary needs",
            schema: { properties: { note: { type: "string" } }, required: [] },
          },
        },
      ],
    },
  };
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, {
    artifactrLog: [...waiting, paused],
  });
  await screen.getByRole("button", { name: "Go to the question" }).click();
  await expect.element(screen.getByRole("form", { name: "Dietary needs" })).toHaveFocus();
});

test("a thread marks itself, with its chat and its sharing, to be blocked whole from a session replay", async () => {
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, {
    artifactrLog: LOG,
  });
  const log = screen.getByRole("log", { name: "Messages" });
  await expect.element(log.getByText("Planned for next week.")).toBeVisible();
  expect(log.element().closest('[data-portalr-replay="block"]')).not.toBeNull();
});

test("a turn under way has a strip with Stop, which asks the run to stop", async () => {
  const sent: { type: string; run_id?: string }[] = [];
  const working = LOG.slice(
    0,
    LOG.findIndex((entry) => entry.event.type === "run_ended" && entry.event.run_id === "run_2"),
  );
  const { screen } = await open(
    "/t/acme/w/notes/threads/thr_1",
    serve,
    (command) => {
      sent.push(command);
      return null;
    },
    { artifactrLog: working },
  );
  const strip = screen.getByRole("group", { name: "This turn" });
  // "Working", and what it is doing once the prefetched add-on has loaded.
  await expect.poll(() => strip.getByRole("status").element().textContent).toMatch(/^Working/);
  await strip.getByRole("button", { name: "Stop" }).click();
  expect(sent.at(-1)).toMatchObject({ type: "stop_run", run_id: "run_2" });
});

test("the thread's mode is switched in its head, where the reader may", async () => {
  const sent: { type: string; thread_id?: string; mode?: string }[] = [];
  const { screen } = await open(
    "/t/acme/w/notes/threads/thr_1",
    serve,
    (command) => {
      sent.push(command);
      return null;
    },
    { artifactrLog: LOG },
  );
  const mode = screen.getByRole("radiogroup", { name: "Agent mode" });
  await expect.element(mode.getByRole("radio", { name: "Auto" })).toBeChecked();
  await mode.getByRole("radio", { name: "Ask" }).click();
  expect(sent.at(-1)).toMatchObject({
    type: "set_thread_mode",
    thread_id: "thr_1",
    mode: "suggest",
  });
});

test("a thread shown live is marked read here, as far as it is active", async () => {
  localStorage.removeItem("portalr:seen:acme/notes");
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, {
    artifactrLog: LOG,
  });
  await expect.element(screen.getByRole("heading", { name: "Launch" })).toBeVisible();
  await expect
    .poll(() => JSON.parse(localStorage.getItem("portalr:seen:acme/notes") ?? "{}"))
    .toEqual({ thr_1: LOG.findLast((entry) => entry.event.type === "message_posted")?.seq });
  localStorage.removeItem("portalr:seen:acme/notes");
});
