/**
 * Usage as a route, over a stubbed portalr: on the rail where reading the tenant's spend is
 * allowed, its spend per day, its tracker against the budget's share where there is one, each
 * workspace's part from artifactr's list, and each of LiteLLM's states.
 */

import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { open as opened } from "./test/admin";

/** The usage reads made, by their query. */
const reads: URLSearchParams[] = [];

/**
 * The test's own now, taken once as it starts, so the days the stub answers and the days the test
 * reads are the same ones, however near a midnight it runs.
 */
let now = new Date();

const days = (count: number, from = now) =>
  Array.from({ length: count }, (_, back) =>
    new Date(from.getTime() - (count - 1 - back) * 86_400_000).toISOString().slice(0, 10),
  );

/** How the next read differs from a week's: no budget, partial, or none. */
let shape: "week" | "unbudgeted" | "partial" = "week";
let litellm: "ok" | "unconfigured" | "unavailable" = "ok";
let artifactr: "ok" | "refused" | "refused-once" = "ok";
/** How many times artifactr's list of workspaces was read. */
let listings = 0;

function usage() {
  const week = days(7);
  const base = {
    days: week.map((day, at) => ({
      day,
      spend: at === 6 ? 5 : at === 5 ? 2 : 0,
      tokens: at === 6 ? 500 : 0,
      requests: at === 6 ? 10 : at === 5 ? 4 : 0,
    })),
    workspaces: [
      { workspace: "notes", spend: 4, tokens: 400 },
      { workspace: "plans", spend: 1, tokens: 100 },
    ],
    budget: { spend: 7, max_budget: 90, budget_duration: "30d" },
    daily_budget: 3,
    complete: true,
  };
  switch (shape) {
    case "unbudgeted":
      return {
        ...base,
        budget: { spend: 7, max_budget: null, budget_duration: null },
        daily_budget: null,
      };
    case "partial":
      // The read never reached the week's first four days: they aren't in the answer.
      return { ...base, complete: false, days: base.days.slice(4) };
    default:
      return base;
  }
}

async function portalr(request: Request, path: string): Promise<Response | undefined> {
  if (path === "/portalr/v1/usage") {
    reads.push(new URL(request.url).searchParams);
    if (litellm === "unconfigured") {
      return Response.json({ status: "unconfigured" });
    }
    if (litellm === "unavailable") {
      return Response.json({ status: "unavailable", reason: "litellm answered 502" });
    }
    return Response.json({ status: "ok", data: usage() });
  }
  if (path === "/portalr/v1/deployment/tenants") {
    return Response.json(
      { detail: { type: "forbidden", message: "not an operator" } },
      { status: 403 },
    );
  }
  if (path === "/artifactr/v1/workspaces") {
    listings += 1;
    // "refused-once": the first read is refused, and any later one would succeed.
    const refused = artifactr === "refused" || (artifactr === "refused-once" && listings === 1);
    return refused
      ? Response.json({ detail: { type: "forbidden", message: "no" } }, { status: 403 })
      : Response.json(["plans", "notes"]);
  }
  return undefined;
}

const open = (path: string, allowed: readonly string[] = ["portalr:read_spend"]) =>
  opened(path, allowed, portalr);

beforeEach(async () => {
  now = new Date();
  await page.viewport(1280, 900);
});

afterEach(() => {
  reads.length = 0;
  shape = "week";
  litellm = "ok";
  artifactr = "ok";
  listings = 0;
  vi.unstubAllGlobals();
});

test("Usage is on the rail where reading spend is allowed, and not found elsewhere", async () => {
  const { screen } = await open("/t/acme/usage", ["portalr:read_telemetry"]);
  await expect.element(screen.getByText("Usage isn't yours to read here")).toBeVisible();
  // It stands in for the screen, so the focus starts on its heading.
  await expect
    .element(screen.getByRole("heading", { name: "Usage isn't yours to read here" }))
    .toHaveFocus();
  const rail = screen.getByRole("navigation", { name: "Tenant" });
  await expect.element(rail.getByRole("link", { name: "Usage" })).not.toBeInTheDocument();
  expect(reads).toEqual([]);
});

test("the week's spend, each day against its share, and each workspace's part", async () => {
  const { screen } = await open("/t/acme");
  await screen
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Usage" })
    .click();
  // The window's spend is the headline, and the donut's total, at the centre of its ring.
  await expect.element(screen.getByText("$7.00").first()).toBeVisible();
  const tracker = screen.getByRole("figure", {
    name: "Each day's spend against its share of the budget: $3.00 a day, of $90.00 over 30 days",
  });
  await expect.element(tracker).toBeVisible();
  await tracker.getByText("Show the figures").click();
  const today = days(7)[6] ?? "";
  await expect
    .element(tracker.getByRole("row", { name: today }))
    .toHaveTextContent(`${today}$5.00Over its share`);
  await expect.element(screen.getByRole("figure", { name: "Spend per day" })).toBeVisible();
  const donut = screen.getByRole("figure", { name: "Spend by workspace" });
  expect(
    donut
      .getByRole("listitem")
      .elements()
      .map((item) => item.textContent),
  ).toEqual(["notes, $4.00, 57%", "No workspace, $2.00, 29%", "plans, $1.00, 14%"]);
  await expect.element(screen.getByText(/has no workspace split/)).toBeVisible();
  // The tenant's workspaces, as artifactr lists them, in order.
  expect(reads.at(-1)?.getAll("workspaces")).toEqual(["notes", "plans"]);
  expect(new Date(reads.at(-1)?.get("start") ?? "").getUTCHours()).toBe(0);
});

test("without a budget, there is no tracker", async () => {
  shape = "unbudgeted";
  const { screen } = await open("/t/acme/usage");
  await expect.element(screen.getByRole("figure", { name: "Spend per day" })).toBeVisible();
  await expect
    .element(screen.getByRole("figure", { name: /against its share of the budget/ }))
    .not.toBeInTheDocument();
});

test("a window goes to portalr and into the address", async () => {
  const { screen, router } = await open("/t/acme/usage");
  await screen.getByRole("radio", { name: "30 days" }).click();
  await expect.poll(() => router.state.location.search).toMatchObject({ days: 30 });
  const start = new Date(reads.at(-1)?.get("start") ?? "");
  const end = new Date(reads.at(-1)?.get("end") ?? "");
  expect((end.getTime() - start.getTime()) / 86_400_000).toBe(30);
});

test("the arrow keys move the window, one step and one read each, and the focus stays on the window", async () => {
  const { screen, router } = await open("/t/acme/usage");
  await screen.getByRole("radio", { name: "7 days" }).click();
  const group = screen.getByRole("radiogroup", { name: "Window" });
  const navigated = vi.fn();
  router.subscribe("onResolved", navigated);
  await userEvent.keyboard("{ArrowRight}");
  await expect.poll(() => router.state.location.search).toMatchObject({ days: 30 });
  await expect.element(screen.getByRole("figure", { name: "Spend per day" })).toBeVisible();
  expect(group.element().contains(document.activeElement)).toBe(true);
  await userEvent.keyboard("{ArrowRight}");
  await expect.poll(() => router.state.location.search).toMatchObject({ days: 90 });
  expect(group.element().contains(document.activeElement)).toBe(true);
  // Two presses, two navigations, none stacked on another.
  expect(navigated.mock.calls.length).toBeLessThanOrEqual(2);
});

test("without artifactr's list, the spend is read whole, and says so", async () => {
  artifactr = "refused";
  const { screen } = await open("/t/acme/usage");
  await expect.element(screen.getByText(/so the spend is read whole/)).toBeVisible();
  expect(reads.at(-1)?.getAll("workspaces")).toEqual([]);
});

test("a partial read says so, with a badge", async () => {
  shape = "partial";
  const { screen } = await open("/t/acme/usage");
  await expect.element(screen.getByText(/days it didn't reach/)).toBeVisible();
  // The four days never reached are no blocks and no bars, not nothing spent.
  const tracker = screen.getByRole("figure", { name: /against its share of the budget/ });
  await tracker.getByText("Show the figures").click();
  // Three days, and the table's header row.
  const rows = 3 + 1;
  await expect.poll(() => tracker.getByRole("row").elements()).toHaveLength(rows);
  // And the part no workspace's tag holds isn't made up from totals of different days.
  const donut = screen.getByRole("figure", { name: "Spend by workspace" });
  expect(
    donut
      .getByRole("listitem")
      .elements()
      .map((item) => item.textContent),
  ).toEqual(["notes, $4.00, 80%", "plans, $1.00, 20%"]);
});

test("LiteLLM not configured says so", async () => {
  litellm = "unconfigured";
  const { screen } = await open("/t/acme/usage");
  await expect.element(screen.getByText("LiteLLM isn't configured")).toBeVisible();
});

test("LiteLLM not answering says why", async () => {
  litellm = "unavailable";
  const { screen } = await open("/t/acme/usage?days=30");
  await expect.element(screen.getByRole("alert")).toHaveTextContent("litellm answered 502");
});

test("the list of workspaces is read once, by the loader: a refusal isn't read again", async () => {
  artifactr = "refused-once";
  const { screen } = await open("/t/acme/usage");
  await expect.element(screen.getByText(/so the spend is read whole/)).toBeVisible();
  // Give a second read, if the page made one, a moment to happen and change what it asked.
  await new Promise((done) => setTimeout(done, 150));
  expect(listings).toBe(1);
  expect(reads.map((asked) => asked.getAll("workspaces"))).toEqual([[]]);
});
