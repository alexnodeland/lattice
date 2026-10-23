/**
 * Adoption as a route, over a stubbed portalr: on the rail where reading the tenant's telemetry
 * is allowed, its people per day, each integration's people, the funnel and retention, and each
 * of the analytics' states, in the kit's own words.
 */

import { afterEach, beforeEach, expect, test } from "vitest";
import { page } from "vitest/browser";
import { open as opened } from "./test/admin";

/** The adoption reads made, by their query. */
const reads: URLSearchParams[] = [];

let analytics: "ok" | "unconfigured" | "unavailable" = "ok";
/** How many of the five reads were made before the deadline: five for a whole answer. */
let read = 5;

function adoption() {
  const whole = {
    active: { window: 4, week: 3, month: 4 },
    days: [
      { day: "2026-10-01", people: 3 },
      { day: "2026-10-02", people: 2 },
    ],
    integrations: [{ integration: "tracker", uses: 9, people: 2 }],
    funnel: { page: 4, thread: 2, message: 1 },
    retention: [4, 1],
  };
  // As portalr answers a read the deadline cut off: each part it didn't reach is null.
  const parts = Object.entries(whole).map(([part, value], at) => [part, at < read ? value : null]);
  return { ...Object.fromEntries(parts), complete: read === 5 };
}

async function portalr(request: Request, path: string): Promise<Response | undefined> {
  if (path === "/portalr/v1/adoption") {
    reads.push(new URL(request.url).searchParams);
    if (analytics === "unconfigured") {
      return Response.json({ status: "unconfigured" });
    }
    if (analytics === "unavailable") {
      return Response.json({ status: "unavailable", reason: "ClickHouse answered 500" });
    }
    return Response.json({ status: "ok", data: adoption() });
  }
  if (path === "/portalr/v1/deployment/tenants") {
    return Response.json(
      { detail: { type: "forbidden", message: "not an operator" } },
      { status: 403 },
    );
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
  analytics = "ok";
  read = 5;
});

test("Adoption is on the rail where reading telemetry is allowed, and not found elsewhere", async () => {
  const { screen } = await open("/t/acme/adoption", ["portalr:read_spend"]);
  await expect
    .element(screen.getByRole("heading", { name: "Adoption isn't yours to read here" }))
    .toHaveFocus();
  const rail = screen.getByRole("navigation", { name: "Tenant" });
  await expect.element(rail.getByRole("link", { name: "Adoption" })).not.toBeInTheDocument();
  expect(reads).toEqual([]);
});

test("the window's people, each integration's, the funnel and retention", async () => {
  const { screen } = await open("/t/acme");
  await screen
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Adoption" })
    .click();
  await expect
    .element(screen.getByRole("article", { name: "In its last 7 days" }))
    .toHaveTextContent("In its last 7 days3");
  await expect.element(screen.getByRole("figure", { name: "People active per day" })).toBeVisible();
  await expect
    .element(screen.getByRole("row", { name: /tracker/ }))
    .toHaveTextContent("tracker250%9");
  await expect
    .element(screen.getByRole("row", { name: /Then sent a message/ }))
    .toHaveTextContent("Then sent a message125%");
  await expect.element(screen.getByRole("row", { name: /Week 2/ })).toHaveTextContent("Week 2125%");
  await expect.element(screen.getByText(/never what they wrote/)).toBeVisible();
  await expect.element(screen.getByText(/wasn't read/)).not.toBeInTheDocument();
  expect(new Date(reads.at(-1)?.get("start") ?? "").getUTCHours()).toBe(0);
});

test.each([
  [1, ["Each day's people", "Each integration's use", "The funnel", "Retention"]],
  [2, ["Each integration's use", "The funnel", "Retention"]],
  [3, ["The funnel", "Retention"]],
])(
  "cut off after %i reads, each part not read says so, and none claims none",
  async (made, unread) => {
    read = made;
    const { screen } = await open("/t/acme/adoption");
    await expect.element(screen.getByText(/The read stopped short/)).toBeVisible();
    for (const part of unread) {
      await expect.element(screen.getByText(`${part} wasn't read`, { exact: false })).toBeVisible();
    }
    await expect.poll(() => screen.getByText(/wasn't read/).elements().length).toBe(unread.length);
    // What was read is shown; nothing unread is shown as none.
    await expect
      .element(screen.getByRole("article", { name: "Over the window" }))
      .toHaveTextContent("Over the window4");
    await expect
      .element(screen.getByText("No integration was used in this window"))
      .not.toBeInTheDocument();
    await expect
      .element(screen.getByText("No one was active in the window's first week"))
      .not.toBeInTheDocument();
    if (made < 2) {
      await expect
        .element(screen.getByRole("figure", { name: "People active per day" }))
        .not.toBeInTheDocument();
    }
  },
);

test("analytics not configured says so", async () => {
  analytics = "unconfigured";
  const { screen } = await open("/t/acme/adoption");
  await expect.element(screen.getByText("Product analytics aren't configured")).toBeVisible();
});

test("analytics not answering says so in the kit's words, never the server's", async () => {
  analytics = "unavailable";
  const { screen } = await open("/t/acme/adoption?days=30");
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("Adoption can't be read just now. Try again in a moment.");
  await expect.element(screen.getByText(/ClickHouse/)).not.toBeInTheDocument();
});
