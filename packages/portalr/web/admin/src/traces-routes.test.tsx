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
let partial = false;

const A = `${"0".repeat(24)}c029eec9`;
const B = `${"0".repeat(24)}c029eeca`;

/** A trace's spans: a turn, and two model calls, each with a prompt it keeps back. */
const spans = (span: string | null) => {
  const model = (id: string, start: number, said: string) => ({
    span_id: id,
    parent_id: "a000000000000001",
    name: `chat ${id}`,
    start_ns: start * 1_000_000,
    end_ns: (start + 40) * 1_000_000,
    attributes: {
      "gen_ai.operation.name": "chat",
      "gen_ai.request.model": "claude",
      ...(span === id ? { "gen_ai.input.messages": said } : {}),
    },
    error: false,
    withheld: span === id ? [] : ["gen_ai.input.messages"],
  });
  return [
    {
      span_id: "a000000000000001",
      parent_id: null,
      name: "turn",
      start_ns: 1_000_000_000,
      end_ns: 1_100_000_000,
      attributes: { "gen_ai.operation.name": "invoke_workflow" },
      error: false,
      withheld: [],
    },
    model("b000000000000001", 1010, '[{"role":"user","content":"Launch on Tuesday."}]'),
    model("b000000000000002", 1060, '[{"role":"user","content":"Second prompt."}]'),
  ];
};

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
  const query = new URL(request.url).searchParams;
  const revealed = query.get("content") === "true" ? query.get("span") : null;
  return Response.json({
    status: "ok",
    data: missing
      ? null
      : { trace_id: path.split("/").at(-1), spans: spans(revealed), complete: !partial },
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
  partial = false;
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
  await screen.getByRole("radio", { name: "24 hours" }).click();
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
  const second = await open(`/t/acme/traces/${A}`);
  await expect.element(second.screen.getByRole("alert")).toHaveTextContent("tempo answered 502");
});

/** The reads that asked for what a span withheld. */
const content = () => reads.filter((read) => read.query.get("content") === "true");

test("a trace is a tree of its spans, and what its spans withheld isn't read until one asks", async () => {
  const { screen } = await open(`/t/acme/traces/${A}`);
  const tree = screen.getByRole("tree", { name: "Spans" });
  await expect.element(tree.getByRole("treeitem", { name: /^turn,/ })).toBeVisible();
  await tree.getByRole("treeitem", { name: /^chat b000000000000001,/ }).click();
  // One read, for the structure: no content, and none asked for.
  expect(reads.map((read) => read.query.has("content"))).toEqual([false]);
  await expect
    .element(screen.getByRole("region", { name: "Withheld" }).getByText("gen_ai.input.messages"))
    .toBeVisible();
});

test("what a span withheld is read for that span alone, when it asks, and another's stays withheld", async () => {
  const { screen } = await open(`/t/acme/traces/${A}`);
  const tree = screen.getByRole("tree", { name: "Spans" });
  await tree.getByRole("treeitem", { name: /^chat b000000000000001,/ }).click();
  const withheld = screen.getByRole("region", { name: "Withheld" });
  await withheld.getByRole("button", { name: "Show what this span withheld" }).click();
  await expect.element(withheld.getByText("Prompt")).toBeVisible();
  await expect.element(withheld.getByText(/Launch on Tuesday/)).toBeVisible();
  // One read for the structure, and one for the span that asked, naming it.
  expect(content().map((read) => read.query.get("span"))).toEqual(["b000000000000001"]);
  expect(reads).toHaveLength(2);
  // The other model call still offers to be asked, and shows nothing of what it withheld.
  await tree.getByRole("treeitem", { name: /^chat b000000000000002,/ }).click();
  const other = screen.getByRole("region", { name: "Withheld" });
  await expect
    .element(other.getByRole("button", { name: "Show what this span withheld" }))
    .toBeVisible();
  await expect.element(screen.getByText(/Second prompt/)).not.toBeInTheDocument();
  await expect.element(screen.getByText(/Launch on Tuesday/)).not.toBeInTheDocument();
  expect(reads).toHaveLength(2);
});

test("another trace starts afresh: nothing asked, nothing read for it, the first span chosen", async () => {
  const { screen, router } = await open(`/t/acme/traces/${A}`);
  const tree = screen.getByRole("tree", { name: "Spans" });
  await tree.getByRole("treeitem", { name: /^chat b000000000000002,/ }).click();
  await screen
    .getByRole("region", { name: "Withheld" })
    .getByRole("button", { name: "Show what this span withheld" })
    .click();
  await expect.element(screen.getByText(/Second prompt/)).toBeVisible();
  expect(content()).toHaveLength(1);
  // Opening another trace: the page is another, and asks for nothing.
  await router.navigate({ to: "/t/$tenant/traces/$trace", params: { tenant: "acme", trace: B } });
  await expect
    .element(
      screen
        .getByRole("region", { name: "Trace" })
        .or(screen.getByRole("heading", { name: "Trace" })),
    )
    .toBeVisible();
  await expect.element(screen.getByRole("region", { name: "turn" })).toBeVisible();
  await expect.element(screen.getByText(/Second prompt/)).not.toBeInTheDocument();
  await expect
    .element(screen.getByRole("treeitem", { name: /^turn,/ }))
    .toHaveAttribute("aria-selected", "true");
  expect(content()).toHaveLength(1);
  // Coming back to the first doesn't keep what was read of it either.
  await router.navigate({ to: "/t/$tenant/traces/$trace", params: { tenant: "acme", trace: A } });
  await screen.getByRole("treeitem", { name: /^chat b000000000000002,/ }).click();
  await expect.element(screen.getByText(/Second prompt/)).not.toBeInTheDocument();
  expect(content()).toHaveLength(1);
});

test("a trace is one read, however its id is written", async () => {
  const { screen } = await open("/t/acme/traces/C029EEC9");
  await expect.element(screen.getByRole("tree", { name: "Spans" })).toBeVisible();
  expect(reads.map((read) => read.path)).toEqual([`/portalr/v1/traces/${A}`]);
});

test("a trace past the spans portalr gives says so", async () => {
  partial = true;
  const { screen } = await open(`/t/acme/traces/${A}`);
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent("This trace has more spans than are shown: these are its first.");
});

test("a trace that isn't there, or isn't the tenant's, or whose id isn't one, says so, and the last isn't read", async () => {
  missing = true;
  const { screen } = await open(`/t/acme/traces/${A}`);
  await expect.element(screen.getByText("No such trace")).toBeVisible();
  reads.length = 0;
  const bad = await open("/t/acme/traces/not%20an%20id");
  await expect.element(bad.screen.getByText("No such trace")).toBeVisible();
  expect(reads).toEqual([]);
});

test("a trace's crumb is a link to Traces, never the page shown", async () => {
  const { screen } = await open(`/t/acme/traces/${A}`);
  const trail = screen.getByRole("navigation", { name: "Breadcrumb" });
  const traces = trail.getByRole("link", { name: "Traces" });
  await expect.element(traces).toBeVisible();
  await expect.element(traces).not.toHaveAttribute("aria-current");
});
