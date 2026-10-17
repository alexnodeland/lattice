/**
 * Tools as a route, over a stubbed portalr: for an operator, the standing notice, the links for the
 * ids given, a link shown only if it is a web address, a tool that isn't there said so, and each
 * ask a read of its own.
 */

import { choose } from "@portalr/ui/testing";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open as opened } from "./test/admin";

/** The link reads made, by their query. */
const asks: URLSearchParams[] = [];
let links: Record<string, string | null> = {};
let refusal: Response | null = null;

const FULL = {
  langfuse_trace: "http://langfuse.test/project/p1/traces/t1",
  langfuse_session: "http://langfuse.test/project/p1/sessions/thr_1",
  langfuse_tenant: "http://langfuse.test/project/p1/traces?filter=x",
  grafana_trace: "http://grafana.test/explore?left=trace",
  grafana_logs: "http://grafana.test/explore?left=run",
  grafana_tenant_logs: "http://grafana.test/explore?left=tenant-logs",
  grafana_tenant_traces: "http://grafana.test/explore?left=tenant-traces",
};

async function portalr(request: Request, path: string): Promise<Response | undefined> {
  if (path === "/portalr/v1/deployment/tenants") {
    return Response.json({ tenants: ["globex", "acme"], spend: { status: "unconfigured" } });
  }
  if (path === "/portalr/v1/deployment/links") {
    asks.push(new URL(request.url).searchParams);
    return refusal ?? Response.json(links);
  }
  if (path === "/artifactr/v1/workspaces") {
    return Response.json([]);
  }
  return undefined;
}

const READERS = {
  tempo: true,
  loki: true,
  prometheus: true,
  langfuse: true,
  litellm: true,
  grafana: true,
};
const open = (path: string, readers: Record<string, boolean> = READERS) =>
  opened(path, [], portalr, ["acme"], { readers });

beforeEach(async () => {
  links = { ...FULL };
  refusal = null;
  asks.length = 0;
  await page.viewport(1280, 900);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("the notice that these tools are outside the gates is on the page, with or without an id", async () => {
  const bare = await open("/deployment/tools");
  const notice = bare.screen.getByRole("complementary", {
    name: "These tools are outside portalr's gates",
  });
  await expect.element(notice).toBeVisible();
  await expect.element(notice.getByText(/Links made here are recorded/)).toBeVisible();
  await bare.screen.unmount();
  const asked = await open("/deployment/tools?trace=t1");
  await expect
    .element(
      asked.screen.getByRole("complementary", { name: "These tools are outside portalr's gates" }),
    )
    .toBeVisible();
});

test("with no id nothing is asked for, and the page says to enter one", async () => {
  const { screen } = await open("/deployment/tools");
  await expect.element(screen.getByText("Enter an id")).toBeVisible();
  expect(asks).toEqual([]);
});

test("the ids in the address make the links they give, each opened in a new tab without an opener", async () => {
  const { screen } = await open("/deployment/tools?trace=t1&session=thr_1&run=run_1&tenant=acme");
  await expect.element(screen.getByRole("link", { name: "The trace in Langfuse" })).toBeVisible();
  expect(asks).toHaveLength(1);
  expect(Object.fromEntries(asks[0] ?? [])).toEqual({
    trace_id: "t1",
    session_id: "thr_1",
    run_id: "run_1",
    tenant_id: "acme",
  });
  const names = [
    "The trace in Langfuse",
    "The trace in Grafana, from Tempo",
    "The session in Langfuse",
    "The run's logs in Grafana, from Loki",
    "The tenant's traces in Langfuse",
    "The tenant's logs in Grafana, from Loki",
    "The tenant's traces in Grafana, from Tempo",
  ];
  for (const name of names) {
    const link = screen.getByRole("link", { name }).element();
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.getAttribute("href")).toMatch(/^http:\/\//);
  }
});

test("only the links an id gives are shown", async () => {
  const { screen } = await open("/deployment/tools?run=run_1");
  await expect
    .element(screen.getByRole("link", { name: "The run's logs in Grafana, from Loki" }))
    .toBeVisible();
  await expect
    .element(screen.getByRole("link", { name: "The trace in Langfuse" }))
    .not.toBeInTheDocument();
});

test("a link that is not a web address is not shown as one", async () => {
  links = {
    ...FULL,
    langfuse_trace: "javascript:alert(1)",
    grafana_trace: "data:text/html,<script>alert(1)</script>",
  };
  const { screen } = await open("/deployment/tools?trace=t1");
  await expect.element(screen.getByText("No link can be made for what was asked.")).toBeVisible();
  expect(
    screen
      .getByRole("link")
      .elements()
      .filter((each) => /javascript|data:/.test(each.getAttribute("href") ?? "")),
  ).toEqual([]);
});

test("a tool that isn't configured says it has no links", async () => {
  links = { ...FULL, langfuse_trace: null, langfuse_session: null };
  const { screen } = await open("/deployment/tools?trace=t1&session=thr_1", {
    ...READERS,
    langfuse: false,
  });
  await expect
    .element(screen.getByText("Langfuse isn't configured here, so it has no links."))
    .toBeVisible();
  await expect
    .element(screen.getByRole("link", { name: "The trace in Grafana, from Tempo" }))
    .toBeVisible();
});

test("asking for others is another page, and each ask is a read of its own", async () => {
  const { screen, router } = await open("/deployment/tools?trace=t1");
  await expect.element(screen.getByRole("link", { name: "The trace in Langfuse" })).toBeVisible();
  await screen.getByRole("textbox", { name: "Trace id" }).fill("t2");
  await choose(screen, "Tenant", "globex");
  await screen.getByRole("button", { name: "Get links" }).click();
  await expect
    .poll(() => router.state.location.search)
    .toMatchObject({ trace: "t2", tenant: "globex" });
  await expect.poll(() => asks.length).toBe(2);
  expect(Object.fromEntries(asks[1] ?? [])).toEqual({ trace_id: "t2", tenant_id: "globex" });
  // Asking for the same again, at once, is the same page: nothing is read twice. Asking for
  // what was asked before is read again, since each ask is recorded and nothing is kept.
  await screen.getByRole("button", { name: "Get links" }).click();
  await screen.getByRole("textbox", { name: "Trace id" }).fill("t1");
  await choose(screen, "Tenant", "No tenant");
  await screen.getByRole("button", { name: "Get links" }).click();
  await expect.poll(() => asks.length).toBe(3);
  expect(Object.fromEntries(asks[2] ?? [])).toEqual({ trace_id: "t1" });
});

test("an id that isn't one is not sent, and the page says it was ignored", async () => {
  const { screen } = await open("/deployment/tools?trace=not%20an%20id&run=run_1");
  await expect
    .element(
      screen.getByText(/“not an id” isn't an id portalr takes, so it was ignored \(Trace id\)\./),
    )
    .toBeVisible();
  // What was good is still asked for, alone.
  await expect.poll(() => asks.length).toBe(1);
  expect(Object.fromEntries(asks[0] ?? [])).toEqual({ run_id: "run_1" });
});

test("an address with only an id that isn't one asks for nothing", async () => {
  const { screen } = await open("/deployment/tools?tenant=a~b");
  await expect.element(screen.getByText("Enter an id")).toBeVisible();
  await expect.element(screen.getByText(/isn't a tenant id portalr takes/)).toBeVisible();
  expect(asks).toEqual([]);
});

test("a refusal is said, with no link", async () => {
  refusal = Response.json(
    { detail: { type: "invalid", message: "no tenant nowhere" } },
    { status: 422 },
  );
  const { screen } = await open("/deployment/tools?tenant=nowhere");
  await expect.element(screen.getByRole("alert")).toBeVisible();
  expect(
    screen
      .getByRole("link")
      .elements()
      .filter((each) => each.getAttribute("target") === "_blank"),
  ).toEqual([]);
});

test("the rail offers Tools to an operator, and someone else is not shown the page", async () => {
  const operator = await open("/deployment");
  await expect
    .element(
      operator.screen
        .getByRole("navigation", { name: "Deployment" })
        .getByRole("link", { name: "Tools" }),
    )
    .toBeVisible();
  await operator.screen.unmount();
  const other = await opened("/deployment/tools", [], async (_request, path) =>
    path === "/portalr/v1/deployment/tenants"
      ? Response.json({ detail: { type: "forbidden", message: "no" } }, { status: 403 })
      : undefined,
  );
  await expect
    .element(other.screen.getByRole("heading", { name: "Tools" }))
    .not.toBeInTheDocument();
});
