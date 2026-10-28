/**
 * A workspace as a route, over a stubbed grantr and artifactr stream: it opens without waiting on
 * its integrations when grantr fails them, reads them once, and again when a command is refused
 * as `not_enabled` (portalr ADR-0045).
 */

import { afterEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { open } from "./test/app";

const FLAGS = "/grantr/v1/tenants/acme/workspaces/notes/enabled-integrations";

/** How often the page asked grantr for the workspace's integrations. */
const reads = (fetched: { mock: { calls: unknown[][] } }) =>
  fetched.mock.calls.filter(([input]) => new URL((input as Request).url).pathname === FLAGS).length;

afterEach(() => {
  vi.unstubAllGlobals();
});

test("with grantr failing, the workspace opens at once, and its integrations are read once", async () => {
  const started = performance.now();
  const { screen, fetched } = await open("/t/acme/w/notes", async (_request, path) =>
    path === FLAGS ? new Response("upstream gone", { status: 503 }) : undefined,
  );
  await expect.element(screen.getByRole("heading", { name: "Threads" })).toBeVisible();
  expect(performance.now() - started).toBeLessThan(1500);
  // The app's query client tries a failed read again after a second: this one isn't.
  await new Promise((waited) => setTimeout(waited, 1500));
  expect(reads(fetched)).toBe(1);
});

test("a command refused as not_enabled reads the workspace's integrations again", async () => {
  const { screen, fetched } = await open(
    "/t/acme/w/notes",
    async (_request, path) => (path === FLAGS ? Response.json({ excalidraw: false }) : undefined),
    (command) => (command.type === "create_thread" ? "not_enabled" : null),
  );
  await expect.poll(() => reads(fetched)).toBe(1);
  await screen.getByRole("button", { name: "Name it first…" }).click();
  await screen.getByRole("textbox", { name: "New thread" }).fill("Sketch");
  await screen.getByRole("button", { name: "Start" }).click();
  await expect
    .element(screen.getByText("The thread wasn't started: the server refused it."))
    .toBeVisible();
  await expect.poll(() => reads(fetched)).toBe(2);
});

test("a thread starts from what is written to the agent: titled by its first line, the message posted, the page moved to it", async () => {
  const sent: { type: string; thread_id?: string; title?: string; content?: string }[] = [];
  const { screen, router } = await open(
    "/t/acme/w/notes",
    async (_request, path) => (path === FLAGS ? Response.json({}) : undefined),
    (command) => {
      sent.push(command);
      return null;
    },
  );
  const message = screen.getByRole("textbox", { name: "Message" });
  await expect.element(message).toBeEnabled();
  await message.fill("Plan the launch\nWe ship on Friday.");
  await screen.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => sent.length).toBe(2);
  const [created, posted] = sent;
  expect(created).toMatchObject({ type: "create_thread", title: "Plan the launch" });
  expect(posted).toMatchObject({
    type: "post_message",
    thread_id: created?.thread_id,
    content: "Plan the launch\nWe ship on Friday.",
  });
  await expect
    .poll(() => router.state.location.pathname)
    .toBe(`/t/acme/w/notes/threads/${created?.thread_id}`);
});

test("a thread refused as it is written keeps the words in the composer", async () => {
  const { screen, router } = await open(
    "/t/acme/w/notes",
    async (_request, path) => (path === FLAGS ? Response.json({}) : undefined),
    (command) => (command.type === "create_thread" ? "forbidden" : null),
  );
  const message = screen.getByRole("textbox", { name: "Message" });
  await expect.element(message).toBeEnabled();
  await message.fill("Plan the launch");
  await screen.getByRole("button", { name: "Send" }).click();
  await expect.element(screen.getByRole("alert")).toBeVisible();
  await expect.element(message).toHaveValue("Plan the launch");
  expect(router.state.location.pathname).toBe("/t/acme/w/notes");
});

test("what waits on a person across the workspace is counted in the bar's corner, a link to those threads", async () => {
  const at = (seq: number, actor: unknown, event: unknown) => ({
    type: "event",
    seq,
    id: `evt_${seq}`,
    ts: "2026-10-20T00:00:00Z",
    workspace_id: "notes",
    actor,
    event,
  });
  const alice = { kind: "user", id: "alice" };
  const agent = (run: string) => ({ kind: "agent", id: "agent", run_id: run });
  const log = [
    at(1, alice, { type: "thread_created", thread_id: "thr_1", title: "Launch" }),
    at(2, alice, { type: "thread_created", thread_id: "thr_2", title: "Invoices" }),
    at(3, agent("run_1"), { type: "run_started", run_id: "run_1", thread_id: "thr_1" }),
    at(4, agent("run_1"), {
      type: "run_paused",
      run_id: "run_1",
      thread_id: "thr_1",
      requests: [
        {
          kind: "question",
          tool_call_id: "q1",
          tool_name: "ask_user",
          args: { questions: [{ question: "When?", options: [{ label: "Now" }] }] },
        },
      ],
    }),
    at(5, agent("run_2"), { type: "run_started", run_id: "run_2", thread_id: "thr_2" }),
    at(6, agent("run_2"), {
      type: "run_paused",
      run_id: "run_2",
      thread_id: "thr_2",
      requests: [
        {
          kind: "approval",
          tool_call_id: "a1",
          tool_name: "run_script",
          args: {},
          review: { app: "Blender", runs: "It runs a script.", risk: "network" },
        },
      ],
    }),
    // A run in a thread the stream never showed the reader: not theirs to open.
    at(7, agent("run_3"), { type: "run_started", run_id: "run_3", thread_id: "thr_hidden" }),
    at(8, agent("run_3"), {
      type: "run_paused",
      run_id: "run_3",
      thread_id: "thr_hidden",
      requests: [{ kind: "question", tool_call_id: "q9", tool_name: "ask_user", args: {} }],
    }),
  ];
  const { screen } = await open(
    "/t/acme/w/notes",
    async (_request, path) => (path === FLAGS ? Response.json({}) : undefined),
    () => null,
    { artifactrLog: log },
  );
  // The bar's corner counts what waits, in the threads the reader can see, and goes to them
  // (portalr ADR-0087).
  const waiting = screen.getByRole("link", { name: "2 need you" });
  await expect.element(waiting).toHaveAttribute("href", "/t/acme/w/notes?show=needs");
  await expect
    .element(screen.getByRole("navigation", { name: "Workspace" }).first())
    .toBeInTheDocument();
});

test("the threads are filtered by state, the view kept in the URL, found from the palette, and one read here that has moved since is marked", async () => {
  const at = (seq: number, actor: unknown, event: unknown) => ({
    type: "event",
    seq,
    id: `evt_${seq}`,
    ts: "2026-10-20T00:00:00Z",
    workspace_id: "notes",
    actor,
    event,
  });
  const alice = { kind: "user", id: "alice" };
  const agent = (run: string) => ({ kind: "agent", id: "agent", run_id: run });
  const log = [
    at(1, alice, { type: "thread_created", thread_id: "thr_1", title: "Launch" }),
    at(2, alice, { type: "thread_created", thread_id: "thr_2", title: "Invoices" }),
    at(3, alice, { type: "message_posted", thread_id: "thr_2", message_id: "m1", content: "Hi" }),
    at(4, agent("run_1"), { type: "run_started", run_id: "run_1", thread_id: "thr_1" }),
  ];
  // Invoices was read here at its start; it has a message since. Launch was never opened here.
  localStorage.setItem("portalr:seen:acme/notes", JSON.stringify({ thr_2: 2 }));
  const { screen, router } = await open(
    "/t/acme/w/notes",
    async (_request, path) => (path === FLAGS ? Response.json({}) : undefined),
    () => null,
    { artifactrLog: log },
  );
  const threads = screen.getByRole("list", { name: "Threads" });
  await expect.element(threads.getByRole("listitem")).toHaveLength(2);
  const invoices = threads.getByRole("listitem").filter({ hasText: "Invoices" });
  await expect
    .element(invoices.getByRole("img", { name: "Moved since you read it" }))
    .toBeVisible();
  expect(
    threads
      .getByRole("listitem")
      .filter({ hasText: "Launch" })
      .getByRole("img", { name: "Moved since you read it" })
      .elements(),
  ).toHaveLength(0);
  // Search is the bar's magnifier, the palette, opened by it or by "/" (portalr ADR-0087); its
  // field finds a thread by its title, Enter goes to it, and Escape gives the focus back.
  const magnifier = screen.getByRole("button", { name: "Search", exact: true });
  await expect.element(magnifier).toHaveAttribute("aria-expanded", "false");
  // Held as the element: while the palette is open the page behind it is out of the
  // accessibility tree, the magnifier with it.
  const trigger = magnifier.element();
  await magnifier.click();
  const field = screen.getByRole("combobox", { name: "Search or go to" });
  await expect.element(field).toBeVisible();
  expect(trigger.getAttribute("aria-expanded")).toBe("true");
  await expect.element(field).toHaveFocus();
  await field.fill("inv");
  await expect
    .element(screen.getByRole("option", { name: "Invoices" }))
    .toHaveAttribute("aria-selected", "true");
  // Its groups are named, each by exactly its heading, and a choice is followed by a click as by
  // Enter.
  await expect.element(screen.getByRole("group", { name: "Threads" })).toBeVisible();
  await field.fill("");
  const groups = [...document.querySelectorAll('[role="listbox"] fieldset')];
  expect(groups.length).toBeGreaterThan(1);
  for (const group of groups) {
    const ids = (group.getAttribute("aria-labelledby") ?? "").split(/\s+/);
    expect(ids).toHaveLength(1);
    const heading = document.getElementById(ids[0] ?? "");
    expect(heading?.textContent).toBe(group.querySelector("div")?.textContent);
  }
  await expect.element(screen.getByRole("group", { name: "Go to" })).toBeVisible();
  await userEvent.keyboard("{Escape}");
  await expect.element(magnifier).toHaveFocus();
  await magnifier.click();
  await screen.getByRole("combobox", { name: "Search or go to" }).fill("rules");
  await screen.getByRole("option", { name: "Rules" }).click();
  await expect.poll(() => router.state.location.pathname).toBe("/t/acme/w/notes/rules");
  await router.navigate({
    to: "/t/$tenant/w/$workspace",
    params: { tenant: "acme", workspace: "notes" },
  });
  (document.activeElement as HTMLElement).blur();
  // "/" opens it from the page, never with Ctrl held.
  await userEvent.keyboard("{Control>}/{/Control}");
  expect(screen.getByRole("combobox").elements()).toHaveLength(0);
  (document.activeElement as HTMLElement).blur();
  await userEvent.keyboard("/");
  await expect.element(screen.getByRole("combobox", { name: "Search or go to" })).toHaveFocus();
  await userEvent.keyboard("inv{Enter}");
  await expect.poll(() => router.state.location.pathname).toBe("/t/acme/w/notes/threads/thr_2");
  await router.navigate({
    to: "/t/$tenant/w/$workspace",
    params: { tenant: "acme", workspace: "notes" },
  });
  await screen.getByRole("radio", { name: /^Working/ }).click();
  await expect.element(threads.getByRole("listitem")).toHaveLength(1);
  await expect.element(threads.getByRole("listitem").filter({ hasText: "Launch" })).toBeVisible();
  await expect.poll(() => router.state.location.search).toEqual({ show: "working" });
  await screen.getByRole("radio", { name: /^Needs you/ }).click();
  await expect.element(screen.getByText("No thread here")).toBeVisible();
  localStorage.removeItem("portalr:seen:acme/notes");
});

test("a thread whose start the connection closes on keeps the words in the composer", async () => {
  const { screen } = await open(
    "/t/acme/w/notes",
    async (_request, path) => (path === FLAGS ? Response.json({}) : undefined),
    (command) => (command.type === "create_thread" ? "close" : null),
  );
  const message = screen.getByRole("textbox", { name: "Message" });
  await expect.element(message).toBeEnabled();
  await message.fill("Plan the launch");
  await screen.getByRole("button", { name: "Send" }).click();
  await expect.element(screen.getByRole("alert").first()).toBeVisible();
  await expect.element(message).toHaveValue("Plan the launch");
});

test("a first message refused after its thread was made keeps the words, and sent again goes to that thread under the same ids", async () => {
  const sent: { type: string; thread_id?: string; message_id?: string }[] = [];
  let posts = 0;
  const { screen, router } = await open(
    "/t/acme/w/notes",
    async (_request, path) => (path === FLAGS ? Response.json({}) : undefined),
    (command) => {
      sent.push(command);
      if (command.type === "post_message") {
        posts += 1;
        return posts === 1 ? "forbidden" : null;
      }
      if (
        command.type === "create_thread" &&
        sent.filter((c) => c.type === "create_thread").length > 1
      ) {
        const { thread_id } = command as unknown as { thread_id: string };
        return {
          type: "invalid_state",
          message: "made",
          reason: "already_exists",
          entity: "thread",
          id: thread_id,
        };
      }
      return null;
    },
  );
  const message = screen.getByRole("textbox", { name: "Message" });
  await expect.element(message).toBeEnabled();
  await message.fill("Plan the launch");
  await screen.getByRole("button", { name: "Send" }).click();
  await expect.element(screen.getByRole("alert")).toBeVisible();
  await expect.element(message).toHaveValue("Plan the launch");
  expect(router.state.location.pathname).toBe("/t/acme/w/notes");
  await screen.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => sent.length).toBe(4);
  expect(sent[2]?.thread_id).toBe(sent[0]?.thread_id);
  expect(sent[3]?.message_id).toBe(sent[1]?.message_id);
  await expect
    .poll(() => router.state.location.pathname)
    .toBe(`/t/acme/w/notes/threads/${sent[0]?.thread_id}`);
});

test("from 1024 pixels the threads are a table whose links Tab reaches, and the arrows move between", async () => {
  const at = (seq: number, event: unknown) => ({
    type: "event",
    seq,
    id: `evt_${seq}`,
    ts: "2026-10-20T00:00:00Z",
    workspace_id: "notes",
    actor: { kind: "user", id: "alice" },
    event,
  });
  await page.viewport(1280, 800);
  const { screen } = await open(
    "/t/acme/w/notes",
    async (_request, path) => (path === FLAGS ? Response.json({}) : undefined),
    () => null,
    {
      artifactrLog: [
        at(1, { type: "thread_created", thread_id: "thr_1", title: "Launch" }),
        at(2, { type: "thread_created", thread_id: "thr_2", title: "Invoices" }),
      ],
    },
  );
  const table = screen.getByRole("table", { name: "Threads" });
  const invoices = table.getByRole("link", { name: "Invoices" });
  await expect.element(invoices).toBeVisible();
  expect(invoices.element().tabIndex).toBe(0);
  expect(table.element().querySelectorAll("[tabindex='-1']")).toHaveLength(0);
  (invoices.element() as HTMLElement).focus();
  await userEvent.keyboard("{ArrowDown}");
  await expect.element(table.getByRole("link", { name: "Launch" })).toHaveFocus();
});
