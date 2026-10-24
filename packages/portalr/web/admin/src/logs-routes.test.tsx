/**
 * Logs as a route, over a stubbed portalr: on the rail where reading the tenant's telemetry is
 * allowed, its records without their lines and a line read when asked, its health charts, and
 * each state of Loki and of Prometheus.
 */

import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open as opened } from "./test/admin";

/** The reads made: their path and their query. */
const reads: { path: string; query: URLSearchParams; tenant: string | null }[] = [];

let loki: "ok" | "unconfigured" | "unavailable" | "empty" = "ok";
let prometheus: "ok" | "unconfigured" | "unavailable" | "empty" = "ok";
let incomplete = false;
let shifted = false;

const ESC = "\u001b";
const A = `1792113515633147000-${"a".repeat(16)}-0`;
const B = `1792113515633146000-${"b".repeat(16)}-0`;
const LINE = `${ESC}[31mboom${ESC}[0m launch on Tuesday ${ESC}[2J`;

const record = (id: string, rest: Record<string, unknown> = {}) => ({
  id,
  time_ns: Number(id.split("-")[0]),
  level: "info",
  service: "docplan",
  thread: null,
  run: null,
  length: 30,
  labels: { service_name: "docplan", tenant_id: "acme" },
  withheld: [],
  line: null,
  ...rest,
});

async function portalr(request: Request, path: string): Promise<Response | undefined> {
  if (path === "/portalr/v1/deployment/tenants") {
    return Response.json({ detail: { type: "forbidden", message: "no" } }, { status: 403 });
  }
  const query = new URL(request.url).searchParams;
  if (path === "/portalr/v1/metrics") {
    reads.push({ path, query, tenant: request.headers.get("x-tenant") });
    if (prometheus === "unconfigured") {
      return Response.json({ status: "unconfigured" });
    }
    if (prometheus === "unavailable") {
      return Response.json({ status: "unavailable", reason: "prometheus answered 502" });
    }
    const start = Date.parse(query.get("start") ?? "") / 1000;
    const data =
      prometheus === "empty"
        ? []
        : Array.from({ length: 6 }, (_, at) => ({
            time: start + at * Number(query.get("step")),
            value: query.get("metric") === "turn_latency" ? 0.5 + at / 10 : at % 3,
          }));
    return Response.json({ status: "ok", data });
  }
  if (path.startsWith("/portalr/v1/logs")) {
    reads.push({ path, query, tenant: request.headers.get("x-tenant") });
    if (loki === "unconfigured") {
      return Response.json({ status: "unconfigured" });
    }
    if (loki === "unavailable") {
      return Response.json({ status: "unavailable", reason: "loki answered 502" });
    }
    if (path === "/portalr/v1/logs") {
      const records =
        loki === "empty"
          ? []
          : [
              record(A, { level: "error", thread: "thr_1", run: "run_9", withheld: ["email"] }),
              record(B),
            ];
      return Response.json({ status: "ok", data: { records, complete: !incomplete } });
    }
    const id = path.split("/").at(-1) ?? "";
    return Response.json({
      status: "ok",
      data: record(id, { line: LINE, length: shifted ? 31 : 30 }),
    });
  }
  return undefined;
}

const open = (
  path: string,
  allowed: readonly string[] = ["portalr:read_telemetry"],
  tenants?: readonly string[],
) => opened(path, allowed, portalr, tenants);

/** The reads of records' lines. */
const lines = () => reads.filter((read) => /\/logs\/[^/]+$/.test(read.path));

beforeEach(async () => {
  reads.length = 0;
  await page.viewport(1280, 900);
});

afterEach(() => {
  reads.length = 0;
  loki = "ok";
  prometheus = "ok";
  incomplete = false;
  shifted = false;
  vi.unstubAllGlobals();
});

test("Logs is on the rail where reading telemetry is allowed, and not found elsewhere", async () => {
  const { screen } = await open("/t/acme/logs", ["grantr:add_member"]);
  await expect.element(screen.getByText("Logs aren't yours to read here")).toBeVisible();
  const rail = screen.getByRole("navigation", { name: "Tenant" });
  await expect.element(rail.getByRole("link", { name: "Logs" })).not.toBeInTheDocument();
  expect(reads).toEqual([]);
});

test("the newest records are listed without their lines, and the charts are drawn with their step said", async () => {
  const { screen } = await open("/t/acme/logs");
  await expect
    .element(screen.getByRole("navigation", { name: "Tenant" }).getByRole("link", { name: "Logs" }))
    .toHaveAttribute("aria-current", "page");
  await expect
    .element(screen.getByRole("listbox", { name: "2 records, newest first" }))
    .toBeVisible();
  await expect.element(screen.getByText(/Launch on Tuesday/i)).not.toBeInTheDocument();
  await expect.element(screen.getByText(/Each point is 1 minute\./)).toBeVisible();
  await expect
    .element(screen.getByRole("figure", { name: "How long a turn takes, at the 95th percentile" }))
    .toBeVisible();
  await expect
    .element(screen.getByRole("figure", { name: "Failed turns in each step" }))
    .toBeVisible();
  const logs = reads.find((read) => read.path === "/portalr/v1/logs");
  expect(logs?.query.get("limit")).toBe("1000");
  const span =
    new Date(logs?.query.get("end") ?? "").getTime() -
    new Date(logs?.query.get("start") ?? "").getTime();
  expect(span / 3_600_000).toBe(1);
  const metrics = reads.filter((read) => read.path === "/portalr/v1/metrics");
  expect(metrics.map((read) => read.query.get("metric")).sort()).toEqual([
    "failed_turns",
    "turn_latency",
  ]);
  expect(metrics.every((read) => read.query.get("step") === "60")).toBe(true);
  // No line was asked for.
  expect(lines()).toEqual([]);
});

test("a line is asked for by its record, once, and shown in its colours; another record's stays out", async () => {
  const { screen } = await open("/t/acme/logs");
  await screen.getByRole("button", { name: "Show this line" }).click();
  const line = screen.getByRole("region", { name: "Line" });
  await expect.element(line.getByText(/launch on Tuesday/)).toBeVisible();
  expect(lines().map((read) => read.path)).toEqual([`/portalr/v1/logs/${A}`]);
  expect(line.element().querySelector("pre")?.textContent).toBe("boom launch on Tuesday ");
  expect((line.element().querySelector("pre span") as HTMLElement).style.color).toBe(
    "var(--ansi-1)",
  );
  await screen
    .getByRole("option", { name: /30 characters$/ })
    .nth(1)
    .click();
  await expect.element(screen.getByRole("button", { name: "Show this line" })).toBeVisible();
  await expect.element(screen.getByText(/launch on Tuesday/)).not.toBeInTheDocument();
  expect(lines()).toHaveLength(1);
});

test("other filters are another page: nothing asked carries over", async () => {
  const { screen, router } = await open("/t/acme/logs");
  await screen.getByRole("button", { name: "Show this line" }).click();
  await expect.element(screen.getByText(/launch on Tuesday/)).toBeVisible();
  expect(lines()).toHaveLength(1);
  await screen.getByRole("textbox", { name: "Thread" }).fill("thr_1");
  await screen.getByRole("button", { name: "Apply" }).click();
  await expect.poll(() => router.state.location.search).toMatchObject({ thread: "thr_1" });
  await expect.element(screen.getByText(/launch on Tuesday/)).not.toBeInTheDocument();
  await expect.element(screen.getByRole("button", { name: "Show this line" })).toBeVisible();
  expect(lines()).toHaveLength(1);
  expect(reads.findLast((read) => read.path === "/portalr/v1/logs")?.query.get("thread")).toBe(
    "thr_1",
  );
});

test("a window and a run go to portalr and into the address, and clearing puts them back", async () => {
  const { screen, router } = await open("/t/acme/logs");
  await screen
    .getByRole("radiogroup", { name: "Window" })
    .getByRole("radio", { name: "6 hours" })
    .click();
  await screen.getByRole("textbox", { name: "Run" }).fill("run_9");
  await screen.getByRole("button", { name: "Apply" }).click();
  await expect.poll(() => router.state.location.search).toMatchObject({ hours: 6, run: "run_9" });
  const logs = reads.findLast((read) => read.path === "/portalr/v1/logs");
  expect(logs?.query.get("run")).toBe("run_9");
  expect(
    (new Date(logs?.query.get("end") ?? "").getTime() -
      new Date(logs?.query.get("start") ?? "").getTime()) /
      3_600_000,
  ).toBe(6);
  await screen.getByRole("button", { name: "Clear" }).click();
  await expect.poll(() => router.state.location.search).toMatchObject({ hours: 6 });
  await expect
    .poll(() => reads.findLast((read) => read.path === "/portalr/v1/logs")?.query.has("run"))
    .toBe(false);
});

test("the health window changes the charts' step, which is said", async () => {
  const { screen, router } = await open("/t/acme/logs");
  await screen
    .getByRole("radiogroup", { name: "Health window" })
    .getByRole("radio", { name: "24 hours" })
    .click();
  await expect.poll(() => router.state.location.search).toMatchObject({ health: 24 });
  await expect.element(screen.getByText(/Each point is 15 minutes\./)).toBeVisible();
  await screen
    .getByRole("radiogroup", { name: "Health window" })
    .getByRole("radio", { name: "7 days" })
    .click();
  await expect.element(screen.getByText(/Each point is 2 hours\./)).toBeVisible();
  expect(reads.findLast((read) => read.path === "/portalr/v1/metrics")?.query.get("step")).toBe(
    "7200",
  );
});

test("a list that isn't all of them says so", async () => {
  incomplete = true;
  const { screen } = await open("/t/acme/logs");
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent(
      "These are the newest: there may be more. A shorter window, or a thread or a run, finds the rest.",
    );
});

test("a window with no records says so", async () => {
  loki = "empty";
  const { screen } = await open("/t/acme/logs");
  await expect.element(screen.getByText("No log records in this window")).toBeVisible();
});

test("a filter with no records says no records match", async () => {
  loki = "empty";
  const { screen } = await open("/t/acme/logs?run=run_9");
  await expect.element(screen.getByText("No records match")).toBeVisible();
});

test("Loki not configured leaves the charts", async () => {
  loki = "unconfigured";
  const { screen } = await open("/t/acme/logs");
  await expect.element(screen.getByText("Loki isn't configured")).toBeVisible();
  await expect
    .element(screen.getByRole("figure", { name: "Failed turns in each step" }))
    .toBeVisible();
});

test("Loki not answering leaves the charts", async () => {
  const warned = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  loki = "unavailable";
  const { screen } = await open("/t/acme/logs");
  // What the reader is told is the tool and to try again; the server's words go to the console.
  // Said politely as it appears, as a failure is, in the tool's words, not the server's.
  await expect
    .element(screen.getByRole("status").filter({ hasText: "Loki isn't answering" }))
    .toBeVisible();
  await expect.element(screen.getByText(/couldn't read from Loki just now/)).toBeVisible();
  expect(screen.getByText("loki answered 502").elements()).toHaveLength(0);
  await expect.poll(() => String(warned.mock.calls)).toContain("loki answered 502");
  await expect
    .element(screen.getByRole("figure", { name: "Failed turns in each step" }))
    .toBeVisible();
});

test("Prometheus not answering leaves the logs", async () => {
  prometheus = "unavailable";
  const { screen } = await open("/t/acme/logs");
  await expect.element(screen.getByRole("listbox")).toBeVisible();
  await expect.element(screen.getByText("Prometheus isn't answering").first()).toBeVisible();
});

test("Prometheus not configured leaves the logs", async () => {
  prometheus = "unconfigured";
  const { screen } = await open("/t/acme/logs");
  await expect.element(screen.getByRole("listbox")).toBeVisible();
  await expect.element(screen.getByText("Prometheus isn't configured").first()).toBeVisible();
});

test("no turns in the window is said for each chart", async () => {
  prometheus = "empty";
  const { screen } = await open("/t/acme/logs");
  await expect.element(screen.getByText("No turns in this window")).toBeVisible();
  await expect.element(screen.getByText("No failed turns in this window")).toBeVisible();
});

test("the times are said to be UTC, and a step with no turn is said to be a gap", async () => {
  const { screen } = await open("/t/acme/logs");
  await expect.element(screen.getByText(/Times are in UTC\./)).toBeVisible();
  await expect.element(screen.getByText(/A step with no turns is a gap\./)).toBeVisible();
});

test("another tenant's page starts with nothing asked, and reads no record of the first's", async () => {
  const { screen, router } = await open(
    "/t/acme/logs",
    ["portalr:read_telemetry"],
    ["acme", "globex"],
  );
  await screen.getByRole("button", { name: "Show this line" }).click();
  await expect.element(screen.getByText(/launch on Tuesday/)).toBeVisible();
  expect(lines().map((read) => [read.tenant, read.path])).toEqual([
    ["acme", `/portalr/v1/logs/${A}`],
  ]);
  await router.navigate({ to: "/t/$tenant/logs", params: { tenant: "globex" }, search: {} });
  await expect.element(screen.getByRole("button", { name: "Show this line" })).toBeVisible();
  await expect.element(screen.getByText(/launch on Tuesday/)).not.toBeInTheDocument();
  // No read was made for globex of a record that acme's page asked for.
  expect(lines().filter((read) => read.tenant === "globex")).toEqual([]);
});

test("a line that isn't the length its record said is not shown", async () => {
  shifted = true;
  const { screen } = await open("/t/acme/logs");
  await screen.getByRole("button", { name: "Show this line" }).click();
  await expect.element(screen.getByText("The read returned no such record.")).toBeVisible();
  await expect.element(screen.getByText(/launch on Tuesday/)).not.toBeInTheDocument();
});
