/**
 * Traces as routes, over a stubbed portalr: on the rail where reading the tenant's telemetry is
 * allowed, the list and its filters, a trace's tree and what was said in it, and each of Tempo's
 * states.
 */

import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open as opened } from "./test/admin";

/** The trace reads made, by their query and their path. */
const reads: { path: string; query: URLSearchParams }[] = [];

let tempo: "ok" | "unconfigured" | "unavailable" = "ok";
/** How many traces the next search finds. */
let found = 2;
let missing = false;

const ID = "0".repeat(24) + "c029eec9";
const spans = (content: boolean) => [
  {
    span_id: "s1",
    parent_id: null,
    name: "turn",
    start_ns: 1_000_000_000,
    end_ns: 1_100_000_000,
    attributes: { "gen_ai.operation.name": "invoke_workflow" },
    error: false,
    withheld: [],
  },
  {
    span_id: "s2",
    parent_id: "s1",
    name: "chat claude",
    start_ns: 1_010_000_000,
    end_ns: 1_060_000_000,
    attributes: {
      "gen_ai.operation.name": "chat",
      "gen_ai.request.model": "claude",
      ...(content
        ? { "gen_ai.output.messages": '[{"role":"assistant","content":"Launch on Tuesday."}]' }
        : {}),
    },
    error: false,
    withheld: content ? [] : ["gen_ai.output.messages"],
  },
];

async function portalr(request: Request, path: string): Promise<Response | undefined> {
  if (!path.startsWith("/portalr/v1/traces")) {
    return path === "/portalr/v1/deployment/tenants"
      ? Response.json({ detail: { type: "forbidden", message: "no" } }, { status: 403 })
      : undefined;
  }
  reads.push({ path, query: new URL(request.url).searchParams });
  if (tempo === "unconfigured") {
    return Response.json({ status: "unconfigured" });
  }
  if (tempo === "unavailable") {
    return Response.json({ status: "unavailable", reason: "tempo answered 502" });
  }
  if (path === "/portalr/v1/traces") {
    return Response.json({
      status: "ok",
      data: Array.from({ length: found }, (_, at) => ({
        trace_id: `${"0".repeat(24)}c029eec${at}`,
        root_service: null,
        root_name: null,
        start_ns: 1_792_105_139_940_000_000 - at * 60_000_000_000,
        duration_ms: at === 0 ? 47 : null,
      })),
    });
  }
  const content = new URL(request.url).searchParams.get("content") === "true";
  return Response.json({
    status: "ok",
    data: missing ? null : { trace_id: ID, spans: spans(content) },
  });
}

const open = (path: string, allowed: readonly string[] = ["portalr:read_telemetry"]) =>
  opened(path, allowed, portalr);

beforeEach(async () => {
  await page.viewport(1280, 900);
});

afterEach(() => {
  reads.length = 0;
  tempo = "ok";
  found = 2;
  missing = false;
  vi.unstubAllGlobals();
});

test("Traces is on the rail where reading telemetry is allowed, and not found elsewhere", async () => {
  const { screen } = await open("/t/acme/traces", ["grantr:add_member"]);
  await expect.element(screen.getByText("Traces aren't yours to read here")).toBeVisible();
  const rail = screen.getByRole("navigation", { name: "Tenant" });
  await expect.element(rail.getByRole("link", { name: "Traces" })).not.toBeInTheDocument();
  expect(reads).toEqual([]);
});

test("the newest traces are listed, each a link to its own page", async () => {
  const { screen, router } = await open("/t/acme");
  await screen
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Traces" })
    .click();
  const table = screen.getByRole("table", { name: "Traces" });
  await expect.element(table).toBeVisible();
  expect(table.getByRole("row").elements()).toHaveLength(3);
  await expect.element(table.getByText("47 ms")).toBeVisible();
  const asked = reads.at(-1)?.query;
  expect(asked?.get("limit")).toBe("100");
  expect(asked?.has("session")).toBe(false);
  expect(
    (new Date(asked?.get("end") ?? "").getTime() - new Date(asked?.get("start") ?? "").getTime()) /
      3_600_000,
  ).toBe(1);
  await table.getByRole("link").first().click();
  await expect
    .poll(() => router.state.location.pathname)
    .toBe(`/t/acme/traces/${"0".repeat(24)}c029eec0`);
});

test("a window, a thread and a run go to portalr and into the address", async () => {
  const { screen, router } = await open("/t/acme/traces");
  await screen.getByRole("combobox", { name: "Window" }).selectOptions("The last 24 hours");
  await screen.getByRole("textbox", { name: "Thread" }).fill("thr_1");
  await screen.getByRole("textbox", { name: "Run" }).fill("run_9");
  await screen.getByRole("button", { name: "Apply" }).click();
  await expect.poll(() => reads.at(-1)?.query.get("session")).toBe("thr_1");
  expect(reads.at(-1)?.query.get("run")).toBe("run_9");
  expect(router.state.location.search).toMatchObject({ hours: 24, thread: "thr_1", run: "run_9" });
  await screen.getByRole("button", { name: "Clear" }).click();
  await expect.poll(() => router.state.location.search).toMatchObject({ hours: 24 });
  await expect.poll(() => reads.at(-1)?.query.has("session")).toBe(false);
});

test("no traces says so, and a filter says which to widen", async () => {
  found = 0;
  const { screen } = await open("/t/acme/traces");
  await expect.element(screen.getByText("No traces in this window")).toBeVisible();
  const filtered = await open("/t/acme/traces?thread=thr_1");
  await expect.element(filtered.screen.getByText("No traces match")).toBeVisible();
});

test("a full list says it is the newest, not all", async () => {
  found = 100;
  const { screen } = await open("/t/acme/traces");
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent(
      "The newest 100 are shown. A shorter window, or a thread or a run, finds the rest.",
    );
});

test("Tempo not configured, or not answering, says so", async () => {
  tempo = "unconfigured";
  const first = await open("/t/acme/traces");
  await expect.element(first.screen.getByText("Tempo isn't configured")).toBeVisible();
  tempo = "unavailable";
  const second = await open(`/t/acme/traces/${ID}`);
  await expect.element(second.screen.getByRole("alert")).toHaveTextContent("tempo answered 502");
});

test("a trace is a tree of its spans, and what was said in a span is read when asked", async () => {
  const { screen } = await open(`/t/acme/traces/${ID}`);
  const tree = screen.getByRole("tree", { name: "Spans" });
  await expect.element(tree.getByRole("treeitem", { name: /^turn,/ })).toBeVisible();
  await tree.getByRole("treeitem", { name: /^chat claude,/ }).click();
  expect(reads).toHaveLength(1);
  expect(reads[0]?.query.get("content")).toBe("false");
  const said = screen.getByRole("region", { name: "What was said" });
  await said.getByRole("button", { name: "Show what was said" }).click();
  await expect.element(said.getByText("Completion")).toBeVisible();
  await expect.element(said.getByText(/Launch on Tuesday/)).toBeVisible();
  // One read for the structure, and one for the content, which was asked for.
  expect(reads.map((read) => read.query.get("content"))).toEqual(["false", "true"]);
  // Another span asking doesn't read again.
  await tree.getByRole("treeitem", { name: /^turn,/ }).click();
  expect(reads).toHaveLength(2);
});

test("a trace that isn't there, or isn't the tenant's, says so", async () => {
  missing = true;
  const { screen } = await open(`/t/acme/traces/${ID}`);
  await expect.element(screen.getByText("No such trace")).toBeVisible();
});
