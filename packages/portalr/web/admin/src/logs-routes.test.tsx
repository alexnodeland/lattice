/**
 * Logs as a route, over a stubbed portalr: on the rail where reading the tenant's telemetry is
 * allowed, its records without their lines and a line read when asked, its health charts, and
 * each state of Loki and of Prometheus.
 */

import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open as opened } from "./test/admin";

/** The reads made: their path and their query. */
const reads: { path: string; query: URLSearchParams }[] = [];

let loki: "ok" | "unconfigured" | "unavailable" | "empty" = "ok";
let prometheus: "ok" | "unconfigured" | "unavailable" | "empty" = "ok";
let incomplete = false;

const ESC = "\u001b";
const A = `1792113515633147000-${"a".repeat(16)}`;
const B = `1792113515633146000-${"b".repeat(16)}`;
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
    reads.push({ path, query });
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
    reads.push({ path, query });
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
    return Response.json({ status: "ok", data: record(id, { line: LINE }) });
  }
  return undefined;
}

const open = (path: string, allowed: readonly string[] = ["portalr:read_telemetry"]) =>
  opened(path, allowed, portalr);

/** The reads of records' lines. */
const lines = () => reads.filter((read) => /\/logs\/[^/]+$/.test(read.path));

beforeEach(async () => {
  await page.viewport(1280, 900);
});

afterEach(() => {
  reads.length = 0;
  loki = "ok";
  prometheus = "ok";
  incomplete = false;
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
  await expect.element(screen.getByText("Each point is 1 minute.")).toBeVisible();
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
  expect(
    reads.at(-1)?.query.get("thread") ??
      reads.findLast((r) => r.path === "/portalr/v1/logs")?.query.get("thread"),
  ).toBe("thr_1");
});

test("a window and a run go to portalr and into the address, and clearing puts them back", async () => {
  const { screen, router } = await open("/t/acme/logs");
  await screen.getByRole("combobox", { name: "Window" }).selectOptions("The last 6 hours");
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
  await screen.getByRole("combobox", { name: "Health window" }).selectOptions("The last 24 hours");
  await expect.poll(() => router.state.location.search).toMatchObject({ health: 24 });
  await expect.element(screen.getByText("Each point is 15 minutes.")).toBeVisible();
  await screen.getByRole("combobox", { name: "Health window" }).selectOptions("The last 7 days");
  await expect.element(screen.getByText("Each point is 2 hours.")).toBeVisible();
  expect(reads.findLast((read) => read.path === "/portalr/v1/metrics")?.query.get("step")).toBe(
    "7200",
  );
});

test("a list that isn't all of them says so, and no records, and a filter with none, say so", async () => {
  incomplete = true;
  const first = await open("/t/acme/logs");
  await expect
    .element(first.screen.getByRole("status"))
    .toHaveTextContent(
      "These are the newest: there may be more. A shorter window, or a thread or a run, finds the rest.",
    );
  await first.screen.unmount();
  loki = "empty";
  const empty = await open("/t/acme/logs");
  await expect.element(empty.screen.getByText("No log records in this window")).toBeVisible();
  await empty.screen.unmount();
  const filtered = await open("/t/acme/logs?run=run_9");
  await expect.element(filtered.screen.getByText("No records match")).toBeVisible();
});

test("Loki not there or not answering leaves the charts, and Prometheus not there leaves the logs", async () => {
  loki = "unconfigured";
  const none = await open("/t/acme/logs");
  await expect.element(none.screen.getByText("Loki isn't configured")).toBeVisible();
  await expect
    .element(none.screen.getByRole("figure", { name: "Failed turns in each step" }))
    .toBeVisible();
  await none.screen.unmount();
  loki = "unavailable";
  const down = await open("/t/acme/logs");
  await expect.element(down.screen.getByRole("alert")).toHaveTextContent("loki answered 502");
  await down.screen.unmount();
  loki = "ok";
  prometheus = "unavailable";
  const slow = await open("/t/acme/logs");
  await expect.element(slow.screen.getByRole("listbox")).toBeVisible();
  await expect.element(slow.screen.getByText("Prometheus isn't answering").first()).toBeVisible();
  await slow.screen.unmount();
  prometheus = "unconfigured";
  const absent = await open("/t/acme/logs");
  await expect
    .element(absent.screen.getByText("Prometheus isn't configured").first())
    .toBeVisible();
  await absent.screen.unmount();
  prometheus = "empty";
  const quiet = await open("/t/acme/logs");
  await expect.element(quiet.screen.getByText("No turns in this window")).toBeVisible();
  await expect.element(quiet.screen.getByText("No failed turns in this window")).toBeVisible();
});
