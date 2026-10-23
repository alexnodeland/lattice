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

let analytics: "ok" | "partial" | "unconfigured" | "unavailable" = "ok";

const adoption = () => ({
  people: 4,
  days: [
    { day: "2026-10-01", people: 3 },
    { day: "2026-10-02", people: 2 },
  ],
  integrations: [{ integration: "tracker", uses: 9, people: 2 }],
  funnel: analytics === "partial" ? null : { page: 4, thread: 2, message: 1 },
  retention: analytics === "partial" ? [] : [4, 1],
  complete: analytics !== "partial",
});

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
  await expect.element(screen.getByText(/4 people were active over the window/)).toBeVisible();
  await expect.element(screen.getByRole("figure", { name: "People active per day" })).toBeVisible();
  await expect
    .element(screen.getByRole("row", { name: /tracker/ }))
    .toHaveTextContent("tracker250%9");
  await expect
    .element(screen.getByRole("row", { name: /Then sent a message/ }))
    .toHaveTextContent("Then sent a message125%");
  await expect.element(screen.getByRole("row", { name: /Week 2/ })).toHaveTextContent("Week 2125%");
  await expect.element(screen.getByText(/never what they wrote/)).toBeVisible();
  expect(new Date(reads.at(-1)?.get("start") ?? "").getUTCHours()).toBe(0);
});

test("a partial read says so, and what it didn't read is empty, not none", async () => {
  analytics = "partial";
  const { screen } = await open("/t/acme/adoption");
  await expect.element(screen.getByText(/The read stopped short/)).toBeVisible();
  await expect.element(screen.getByText("The funnel wasn't read")).toBeVisible();
});

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
