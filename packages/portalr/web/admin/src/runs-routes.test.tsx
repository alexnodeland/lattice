/**
 * Runs as a route, over a stubbed portalr and a stubbed reflexr stream: on the rail where reading
 * runs is allowed, the runs that need someone and every run, each action confirmed and sent once,
 * what people did to a run, and one stream, for the workspace shown, closed with it.
 */

import type { ReflexrV1 } from "@portalr/client";
import { RUN_EVENTS } from "@portalr/client";
import { choose } from "@portalr/ui/testing";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open as opened } from "./test/admin";
import { FakeSocket, frame, type Script, type Sent, stubSockets } from "./test/socket";

const ALICE = { kind: "user", id: "alice" } as const;

/** The log: a run that failed every attempt, one waiting to try again, a running one and a done one. */
const LOG: ReflexrV1.EventFrame[] = [
  frame(1, { type: "reflexr:run_started", run_id: "run_dead", rule: "portalr:triage", attempt: 1 }),
  frame(2, {
    type: "reflexr:run_dead_lettered",
    run_id: "run_dead",
    rule: "portalr:triage",
    attempts: 5,
    error: "boom: a customer's secret",
    reason: "guardrail_blocked",
  }),
  frame(3, { type: "reflexr:run_started", run_id: "run_wait", rule: "portalr:triage", attempt: 1 }),
  frame(4, {
    type: "reflexr:run_retrying",
    run_id: "run_wait",
    rule: "portalr:triage",
    attempt: 2,
    error: "boom",
    next_attempt_at: "2026-10-15T09:10:00Z",
  }),
  frame(5, { type: "reflexr:run_started", run_id: "run_busy", rule: "portalr:triage", attempt: 1 }),
  frame(6, { type: "reflexr:run_started", run_id: "run_done", rule: "ops:page", attempt: 1 }),
  frame(7, { type: "reflexr:run_succeeded", run_id: "run_done", rule: "ops:page" }),
] as ReflexrV1.EventFrame[];

const EVERY = ["reflexr:read_runs", "reflexr:retry_run", "reflexr:skip_run", "reflexr:cancel_run"];

let script: Script;
let next = 8;

/** The server's way with a command: it is carried out, and the log says so. */
const carriedOut: Script["answer"] = ({ command }) => {
  const rule = "portalr:triage";
  const event =
    command.type === "retry_run"
      ? { type: "reflexr:run_requeued", run_id: command.run_id, rule }
      : command.type === "skip_run"
        ? { type: "reflexr:run_skipped", run_id: command.run_id, rule, reason: command.reason }
        : { type: "reflexr:run_cancelled", run_id: command.run_id, rule, reason: command.reason };
  next += 1;
  return {
    result: { ok: true },
    after: [frame(next, event as ReflexrV1.EventFrame["event"], ALICE)],
  };
};

async function portalr(_request: Request, path: string): Promise<Response | undefined> {
  if (path === "/portalr/v1/deployment/tenants") {
    return Response.json({ detail: { type: "forbidden", message: "no" } }, { status: 403 });
  }
  if (path === "/artifactr/v1/workspaces") {
    return Response.json(["notes", "plans"]);
  }
  return undefined;
}

const open = (path: string, allowed: readonly string[] = EVERY) => opened(path, allowed, portalr);

/** relayr's read of what the runs in notes filed: one item, by the chain every run here is in. */
async function filed(request: Request, path: string): Promise<Response | undefined> {
  if (path === "/relayr/v1/workspaces/notes/tracker/items") {
    expect(request.headers.get("x-tenant")).toBe("acme");
    return Response.json({
      tracker: "plane",
      items: [
        {
          key: "dead-letter/run_dead",
          project: "p",
          id: "i1",
          number: 12,
          name: "OPS-12",
          link: "https://plane.example/acme/browse/OPS-12/",
          deleted: false,
          chains: ["c"],
        },
      ],
    });
  }
  return portalr(request, path);
}

const confirm = (
  screen: Awaited<ReturnType<typeof open>>["screen"],
  title: string,
  button: string,
) => screen.getByRole("alertdialog", { name: title }).getByRole("button", { name: button });

const row = (screen: Awaited<ReturnType<typeof open>>["screen"], run: string) =>
  screen.getByRole("table", { name: "Rules' runs" }).getByRole("row", { name: `Run ${run}` });

const commands = (): Sent[] => FakeSocket.sent;

beforeEach(async () => {
  script = { log: LOG, answer: carriedOut };
  next = 8;
  stubSockets(script);
  await page.viewport(1280, 900);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("Runs is on the rail where reading runs is allowed, and not found elsewhere", async () => {
  const { screen } = await open("/t/acme/runs", ["grantr:add_member"]);
  await expect.element(screen.getByText("Runs aren't yours to see here")).toBeVisible();
  await expect
    .element(screen.getByRole("navigation", { name: "Tenant" }).getByRole("link", { name: "Runs" }))
    .not.toBeInTheDocument();
  expect(FakeSocket.sockets).toEqual([]);
});

test("the runs that need someone are listed, with which dead letters they are", async () => {
  const { screen } = await open("/t/acme/runs");
  await expect.element(row(screen, "run_dead")).toBeVisible();
  await expect.element(row(screen, "run_wait")).toBeVisible();
  await expect.element(row(screen, "run_busy")).not.toBeInTheDocument();
  await expect.element(row(screen, "run_done")).not.toBeInTheDocument();
  await expect
    .element(row(screen, "run_dead").getByRole("status"))
    .toHaveTextContent("Dead-lettered");
  await expect.element(row(screen, "run_wait").getByRole("status")).toHaveTextContent("Retrying");
  await expect.element(screen.getByText(/rule's run that failed every attempt/)).toBeVisible();
  // Why it last failed is a code; the error, which may hold what a person said, is not here.
  await expect
    .element(row(screen, "run_dead").getByText(/last failure: guardrail_blocked/))
    .toBeVisible();
  await expect.element(screen.getByText(/secret/)).not.toBeInTheDocument();
});

test("a run links to what its chain filed in the tracker, where the application has one", async () => {
  const relayr = {
    surfaces: {
      artifactr: "/artifactr/v1",
      reflexr: "/reflexr/v1",
      grantr: "",
      portalr: "",
      relayr: "",
    },
  };
  const { screen } = await opened("/t/acme/runs", EVERY, filed, ["acme"], relayr);
  const link = row(screen, "run_dead").getByRole("link", {
    name: "OPS-12, in Plane (opens in a new tab)",
  });
  await expect.element(link).toHaveAttribute("href", "https://plane.example/acme/browse/OPS-12/");
  await expect.element(row(screen, "run_dead").getByText("Filed as")).toBeVisible();
});

test("with no tracker, a run links to none, and relayr is never asked", async () => {
  const { screen } = await open("/t/acme/runs");
  await expect.element(row(screen, "run_dead")).toBeVisible();
  await expect.element(screen.getByText("Filed as")).not.toBeInTheDocument();
  const asked = vi.mocked(fetch).mock.calls.map(([input]) => String(input));
  expect(asked.filter((url) => url.includes("/relayr/"))).toEqual([]);
});

test("every state may be shown, and each offers what its state takes", async () => {
  const { screen } = await open("/t/acme/runs?show=all");
  await expect.element(row(screen, "run_busy")).toBeVisible();
  await expect.element(row(screen, "run_done")).toBeVisible();
  const names = (run: string) =>
    row(screen, run)
      .getByRole("button")
      .elements()
      .map((button) => button.textContent);
  expect(names("run_dead")).toEqual([
    "Retry run run_dead",
    "Skip run run_dead",
    "Cancel run run_dead",
  ]);
  expect(names("run_busy")).toEqual(["Cancel run run_busy"]);
  expect(names("run_done")).toEqual([]);
});

test("a person who may read runs but not act sees no action", async () => {
  const { screen } = await open("/t/acme/runs", ["reflexr:read_runs"]);
  await expect.element(row(screen, "run_dead")).toBeVisible();
  expect(row(screen, "run_dead").getByRole("button").elements()).toEqual([]);
});

test("a retry is confirmed, sent once, and shows who did it", async () => {
  const { screen } = await open("/t/acme/runs?show=all");
  await row(screen, "run_dead").getByRole("button", { name: "Retry run run_dead" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Retry this run?" });
  await expect.element(dialog).toBeVisible();
  // Nothing was sent by asking.
  expect(commands()).toEqual([]);
  await confirm(screen, "Retry this run?", "Retry the run").click();
  await expect.element(row(screen, "run_dead").getByRole("status")).toHaveTextContent("Queued");
  expect(commands().map((sent) => sent.command)).toEqual([
    { type: "retry_run", run_id: "run_dead" },
  ]);
  await row(screen, "run_dead")
    .getByText(/History \(1\)/)
    .click();
  await expect
    .element(row(screen, "run_dead").getByText(/alice made it runnable again/))
    .toBeVisible();
});

test("a skip takes a reason, which goes with the command and stays in the history", async () => {
  const { screen } = await open("/t/acme/runs?show=all");
  await row(screen, "run_dead").getByRole("button", { name: "Skip run run_dead" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Skip this run?" });
  await dialog.getByRole("textbox", { name: "Reason (optional)" }).fill("a known outage");
  await confirm(screen, "Skip this run?", "Skip the run").click();
  await expect.element(row(screen, "run_dead").getByRole("status")).toHaveTextContent("Skipped");
  expect(commands().at(-1)?.command).toEqual({
    type: "skip_run",
    run_id: "run_dead",
    reason: "a known outage",
  });
  await row(screen, "run_dead")
    .getByText(/History \(1\)/)
    .click();
  await expect.element(row(screen, "run_dead").getByText(/alice skipped it/)).toBeVisible();
  await expect.element(row(screen, "run_dead").getByText(/a known outage/)).toBeVisible();
});

test("a cancel takes a reason too, and a retry takes none", async () => {
  const { screen } = await open("/t/acme/runs?show=all");
  await row(screen, "run_busy").getByRole("button", { name: "Cancel run run_busy" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Cancel this run?" });
  await dialog.getByRole("textbox", { name: "Reason (optional)" }).fill("not needed");
  await confirm(screen, "Cancel this run?", "Cancel run").click();
  await expect.element(row(screen, "run_busy").getByRole("status")).toHaveTextContent("Cancelled");
  expect(commands().at(-1)?.command).toEqual({
    type: "cancel_run",
    run_id: "run_busy",
    reason: "not needed",
  });
  await row(screen, "run_dead").getByRole("button", { name: "Retry run run_dead" }).click();
  expect(
    screen.getByRole("alertdialog", { name: "Retry this run?" }).getByRole("textbox").elements(),
  ).toEqual([]);
});

test("a run that leaves the list needing attention returns focus to the list's heading", async () => {
  const { screen } = await open("/t/acme/runs");
  await row(screen, "run_dead").getByRole("button", { name: "Retry run run_dead" }).click();
  await confirm(screen, "Retry this run?", "Retry the run").click();
  await expect.element(row(screen, "run_dead")).not.toBeInTheDocument();
  await expect.element(screen.getByRole("heading", { name: "Rules' runs in notes" })).toHaveFocus();
});

test("a refusal is said, the dialog stays, and a new try is a new command", async () => {
  script.answer = () => ({ result: { ok: false, rejection: { type: "invalid_state" } } });
  const { screen } = await open("/t/acme/runs");
  await row(screen, "run_wait").getByRole("button", { name: "Cancel run run_wait" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Cancel this run?" });
  await dialog.getByRole("button", { name: "Cancel run" }).click();
  await expect
    .element(dialog.getByRole("alert"))
    .toHaveTextContent(
      "The run has changed, and can't take this now: what it is now is shown above.",
    );
  await dialog.getByRole("button", { name: "Cancel run" }).click();
  await expect.poll(() => commands().length).toBe(2);
  expect(new Set(commands().map((sent) => sent.id)).size).toBe(2);
});

test("a command the connection lost the answer to is sent again under the same id, while the dialog is open", async () => {
  script.answer = () => null;
  const { screen, signed } = await open("/t/acme/runs");
  await row(screen, "run_dead").getByRole("button", { name: "Retry run run_dead" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Retry this run?" });
  await dialog.getByRole("button", { name: "Retry the run" }).click();
  await expect.poll(() => commands().length).toBe(1);
  // The server refuses the connection for good: the answer will never come, and the page says so.
  FakeSocket.sockets[0]?.end(4401);
  await expect
    .element(dialog.getByRole("alert"))
    .toHaveTextContent(
      "The connection ended before the server answered. Try again: it is carried out once.",
    );
  // A refreshed session connects again; trying again, in the same dialog, is the same command.
  signed.changed("refreshed");
  await expect.poll(() => FakeSocket.sockets.filter((each) => each.open).length).toBe(1);
  await expect.element(dialog.getByRole("button", { name: "Retry the run" })).toBeEnabled();
  await dialog.getByRole("button", { name: "Retry the run" }).click();
  await expect.poll(() => commands().length).toBe(2);
  expect(commands()[1]?.id).toBe(commands()[0]?.id);
  // Dismissed, it is that intention's alone: a later try is a new command.
  FakeSocket.sockets.find((each) => each.open)?.end(4401);
  await expect.element(dialog.getByRole("alert")).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  signed.changed("refreshed");
  await expect.poll(() => FakeSocket.sockets.filter((each) => each.open).length).toBe(1);
  await row(screen, "run_dead").getByRole("button", { name: "Retry run run_dead" }).click();
  await confirm(screen, "Retry this run?", "Retry the run").click();
  await expect.poll(() => commands().length).toBe(3);
  expect(commands()[2]?.id).not.toBe(commands()[0]?.id);
});

test("an answered command ends its id: the same run retried again is a new command", async () => {
  script.answer = () => ({ result: { ok: true } });
  const { screen } = await open("/t/acme/runs");
  for (const again of [1, 2]) {
    await row(screen, "run_dead").getByRole("button", { name: "Retry run run_dead" }).click();
    await confirm(screen, "Retry this run?", "Retry the run").click();
    await expect.poll(() => commands().length).toBe(again);
  }
  expect(new Set(commands().map((sent) => sent.id)).size).toBe(2);
});

test("only the run events are asked for, so no other event's body reaches the page", async () => {
  const { screen } = await open("/t/acme/runs");
  await expect.element(row(screen, "run_dead")).toBeVisible();
  expect(FakeSocket.hellos.map((hello) => hello.types)).toEqual([[...RUN_EVENTS]]);
});

test("one stream is open, for the workspace shown, and it is closed with the page and on a switch", async () => {
  const { screen, router } = await open("/t/acme/runs");
  await expect.element(row(screen, "run_dead")).toBeVisible();
  expect(FakeSocket.sockets.filter((each) => each.open)).toHaveLength(1);
  expect(FakeSocket.sockets[0]?.url).toContain("/workspaces/notes/stream");
  await choose(screen, "Workspace", "plans");
  await expect.poll(() => router.state.location.search).toMatchObject({ workspace: "plans" });
  await expect.poll(() => FakeSocket.sockets.at(-1)?.url).toContain("/workspaces/plans/stream");
  expect(FakeSocket.sockets.filter((each) => each.open)).toHaveLength(1);
  expect(FakeSocket.sockets[0]?.open).toBe(false);
  await screen.unmount();
  expect(FakeSocket.sockets.filter((each) => each.open)).toEqual([]);
});

test("a workspace the tenant doesn't have is not found, and opens no stream", async () => {
  const { screen } = await open("/t/acme/runs?workspace=ghost");
  await expect.element(screen.getByText("No such workspace")).toBeVisible();
  expect(FakeSocket.sockets).toEqual([]);
  await expect
    .element(screen.getByRole("combobox", { name: "Workspace" }))
    .toHaveTextContent("Choose a workspace");
});

test("the session ending closes the stream, and a refreshed one connects again", async () => {
  const { screen, signed } = await open("/t/acme/runs");
  await expect.element(row(screen, "run_dead")).toBeVisible();
  signed.changed("ended");
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("The connection to this workspace ended. Reload the page to connect again.");
  expect(FakeSocket.sockets.filter((each) => each.open)).toEqual([]);
  signed.changed("refreshed");
  await expect.poll(() => FakeSocket.sockets.filter((each) => each.open).length).toBe(1);
  await expect.element(screen.getByRole("alert")).not.toBeInTheDocument();
});

test("the connection ending for good is said, in words of the page's own", async () => {
  const { screen } = await open("/t/acme/runs");
  await expect.element(row(screen, "run_dead")).toBeVisible();
  FakeSocket.sockets[0]?.end(4401);
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("The connection to this workspace ended. Reload the page to connect again.");
});

test("regression guard: what the server says in an error frame is not put on the page", async () => {
  const { screen } = await open("/t/acme/runs");
  await expect.element(row(screen, "run_dead")).toBeVisible();
  FakeSocket.sockets[0]?.raw({
    type: "error",
    message: "not a command frame: a customer's secret",
  });
  await expect.element(screen.getByText(/secret/)).not.toBeInTheDocument();
  await expect.element(screen.getByRole("alert")).not.toBeInTheDocument();
});

test("no run needing attention is said, and every state can be shown", async () => {
  script.log = LOG.filter((each) => each.seq >= 6);
  const { screen, router } = await open("/t/acme/runs");
  await expect.element(screen.getByText("No run needs attention")).toBeVisible();
  await screen.getByRole("radio", { name: "Every state" }).click();
  await expect.poll(() => router.state.location.search).toMatchObject({ show: "all" });
  await expect.element(row(screen, "run_done")).toBeVisible();
  await expect.element(screen.getByText("No run needs attention")).not.toBeInTheDocument();
});
