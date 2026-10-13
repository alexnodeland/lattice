/**
 * Feedback as a route, over a stubbed portalr: on the rail where reading the tenant's telemetry
 * is allowed, its charts and tables from portalr's summary, each of Langfuse's states, and, for
 * operators, Langfuse's page for each comment's trace.
 */

import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open as opened } from "./test/admin";

/** The feedback reads made, by their query. */
const reads: URLSearchParams[] = [];

const days = (count: number, from = new Date()) =>
  Array.from({ length: count }, (_, back) =>
    new Date(from.getTime() - (count - 1 - back) * 86_400_000).toISOString().slice(0, 10),
  );

/** portalr's summary of a week: thumbs on two days, two evaluations, and two workspaces. */
function summary() {
  const week = days(7);
  return {
    days: week.map((day, at) => ({
      day,
      up: at === 6 ? 3 : at === 5 ? 1 : 0,
      down: at === 6 ? 1 : 0,
    })),
    evaluations: [
      {
        evaluator: "accuracy",
        name: "accuracy",
        count: 4,
        days: week.map((day, at) => ({ day, count: at > 4 ? 2 : 0, mean: at > 4 ? 0.75 : null })),
      },
      {
        evaluator: "safety",
        name: "safe",
        count: 1,
        days: week.map((day, at) => ({ day, count: at === 6 ? 1 : 0, mean: at === 6 ? 1 : null })),
      },
    ],
    workspaces: [
      { workspace: "notes", up: 3, down: 1, evaluated: 4 },
      { workspace: null, up: 1, down: 0, evaluated: 1 },
    ],
    comments: [
      {
        id: "s1",
        trace_id: "t_1",
        name: "thumbs",
        data_type: "BOOLEAN",
        value: false,
        source: "API",
        timestamp: `${week[6]}T09:00:00Z`,
        comment: "It missed the deadline",
        evaluator: null,
        workspace: "notes",
      },
    ],
    complete: true,
  };
}

let langfuse: "ok" | "unconfigured" | "unavailable" = "ok";
let operator = false;

async function portalr(request: Request, path: string): Promise<Response | undefined> {
  if (path === "/portalr/v1/feedback") {
    reads.push(new URL(request.url).searchParams);
    if (langfuse === "unconfigured") {
      return Response.json({ status: "unconfigured" });
    }
    if (langfuse === "unavailable") {
      return Response.json({ status: "unavailable", reason: "langfuse answered 502" });
    }
    return Response.json({ status: "ok", data: summary() });
  }
  if (path === "/portalr/v1/deployment/tenants") {
    return operator
      ? Response.json({ tenants: ["acme"], spend: { status: "unconfigured" } })
      : Response.json(
          { detail: { type: "forbidden", message: "not an operator" } },
          { status: 403 },
        );
  }
  if (path === "/portalr/v1/deployment/links") {
    const trace = new URL(request.url).searchParams.get("trace_id");
    return Response.json({ langfuse_trace: `http://langfuse.test/traces/${trace}` });
  }
  return undefined;
}

const open = (path: string, allowed: readonly string[] = ["portalr:read_telemetry"]) =>
  opened(path, allowed, portalr);

beforeEach(async () => {
  await page.viewport(1280, 900);
});

afterEach(() => {
  reads.length = 0;
  langfuse = "ok";
  operator = false;
  vi.unstubAllGlobals();
});

test("Feedback is on the rail where reading telemetry is allowed, and not found elsewhere", async () => {
  const { screen } = await open("/t/acme/feedback", ["grantr:add_member"]);
  await expect.element(screen.getByText("Feedback isn't yours to read here")).toBeVisible();
  const rail = screen.getByRole("navigation", { name: "Tenant" });
  await expect.element(rail.getByRole("link", { name: "Feedback" })).not.toBeInTheDocument();
  expect(reads).toEqual([]);
});

test("the week's thumbs, evaluations and workspaces, from portalr's summary", async () => {
  const { screen } = await open("/t/acme");
  await screen
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Feedback" })
    .click();
  await expect
    .element(screen.getByRole("figure", { name: "People's thumbs per day" }))
    .toBeVisible();
  await expect
    .element(screen.getByRole("figure", { name: "Each evaluation's mean per day" }))
    .toBeVisible();
  await expect.element(screen.getByText("accuracy · accuracy").first()).toBeVisible();
  const donut = screen.getByRole("figure", { name: "People's thumbs by workspace" });
  await expect.element(donut.getByRole("listitem").first()).toHaveTextContent("notes4 · 80%");
  const places = screen.getByRole("table", { name: "By workspace" });
  await expect.element(places.getByRole("rowheader", { name: "In no workspace" })).toBeVisible();
  const said = screen.getByRole("table", { name: "What people said" });
  await expect
    .element(said.getByRole("rowheader", { name: "It missed the deadline" }))
    .toBeVisible();
  // Not an operator: the trace's id, with no link out.
  await expect.element(said.getByRole("link")).not.toBeInTheDocument();
  const asked = reads.at(-1);
  expect(asked?.has("workspace")).toBe(false);
  expect(new Date(asked?.get("start") ?? "").getUTCHours()).toBe(0);
});

test("a workspace and a window go to portalr and into the address", async () => {
  const { screen, router } = await open("/t/acme/feedback");
  await screen.getByRole("combobox", { name: "Window" }).selectOptions("The last 30 days");
  await screen.getByRole("combobox", { name: "Workspace" }).selectOptions("notes");
  await expect.poll(() => reads.at(-1)?.get("workspace")).toBe("notes");
  expect(router.state.location.search).toMatchObject({ days: 30, workspace: "notes" });
  const start = new Date(reads.at(-1)?.get("start") ?? "");
  const end = new Date(reads.at(-1)?.get("end") ?? "");
  expect((end.getTime() - start.getTime()) / 86_400_000).toBe(30);
  // One workspace's: no share by workspace.
  await expect
    .element(screen.getByRole("figure", { name: "People's thumbs by workspace" }))
    .not.toBeInTheDocument();
});

test("for an operator, each comment's trace opens in Langfuse", async () => {
  operator = true;
  const { screen } = await open("/t/acme/feedback");
  const link = screen
    .getByRole("table", { name: "What people said" })
    .getByRole("link", { name: "t_1" });
  await expect.element(link).toHaveAttribute("href", "http://langfuse.test/traces/t_1");
});

test("Langfuse not configured says so", async () => {
  langfuse = "unconfigured";
  const { screen } = await open("/t/acme/feedback");
  await expect.element(screen.getByText("Langfuse isn't configured")).toBeVisible();
});

test("Langfuse not answering says why", async () => {
  langfuse = "unavailable";
  const { screen } = await open("/t/acme/feedback?days=30");
  await expect.element(screen.getByRole("alert")).toHaveTextContent("langfuse answered 502");
});
