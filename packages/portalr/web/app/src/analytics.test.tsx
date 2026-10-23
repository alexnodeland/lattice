/**
 * Product analytics in the app (lattice RFC-0008): off until the person turns it on in the account
 * menu, and then each page they open, by the router's name for its route, in their tenant.
 */

import { afterEach, expect, test, vi } from "vitest";
import { routeOf } from "./analytics";
import { open } from "./test/app";
import { FLAGS } from "./test/files";

interface Relay {
  given: boolean;
  deletes?: boolean;
  readonly events: { tenant: string | null; body: unknown }[];
  answers: boolean[];
}

function serving(relay: Relay) {
  return async (request: Request, path: string) => {
    if (path === "/grantr/v1/checks") {
      return Response.json(((await request.json()) as unknown[]).map(() => true));
    }
    if (path === FLAGS) {
      return Response.json({});
    }
    if (path.endsWith("/workspaces/notes/artifacts")) {
      return Response.json([]);
    }
    if (path === "/portalr/v1/analytics/consent") {
      if (request.method === "PUT") {
        relay.given = ((await request.json()) as { given: boolean }).given;
        relay.answers.push(relay.given);
        return Response.json({ given: relay.given, deleted: relay.given ? null : relay.deletes });
      }
      return Response.json({ given: relay.given });
    }
    if (path === "/portalr/v1/analytics/session") {
      return Response.json({ session: "signed" });
    }
    if (path === "/portalr/v1/events") {
      relay.events.push({ tenant: request.headers.get("x-tenant"), body: await request.json() });
      return Response.json({ recorded: 1, dropped: 0 }, { status: 202 });
    }
    return undefined;
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("a page is named by its route, not its address", () => {
  expect(routeOf("/t/$tenant/w/$workspace/runs/")).toBe("/t/$tenant/w/$workspace/runs");
  expect(routeOf("/")).toBe("/");
  expect(routeOf("")).toBe("/");
});

test("without analytics in the deployment there is no switch, and nothing is asked or sent", async () => {
  const relay: Relay = { given: true, events: [], answers: [] };
  const { screen, fetched } = await open("/t/acme/w/notes", serving(relay));
  await screen.getByRole("button", { name: /^Account/ }).click();
  await expect
    .element(screen.getByRole("menuitemcheckbox", { name: "Colour-blind friendly charts" }))
    .toBeVisible();
  expect(
    screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }).elements(),
  ).toHaveLength(0);
  const asked = fetched.mock.calls.map(([input]) => String(input));
  expect(asked.some((url) => url.includes("/portalr/v1/analytics"))).toBe(false);
  expect(relay.events).toEqual([]);
});

test("off until turned on, then the page the person is on is sent, by its route, in the tenant", async () => {
  const relay: Relay = { given: false, events: [], answers: [] };
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, {
    readers: { analytics: true },
  });
  await screen.getByRole("button", { name: /^Account/ }).click();
  const share = screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" });
  await expect.element(share).toHaveAttribute("aria-checked", "false");
  expect(relay.events).toEqual([]);
  await share.click();
  await expect.poll(() => relay.answers).toEqual([true]);
  await expect.poll(() => relay.events.length, { timeout: 10_000 }).toBe(1);
  expect(relay.events[0]).toEqual({
    tenant: "acme",
    body: {
      session: "signed",
      events: [{ event: "app.page.viewed.v1", route: "/t/$tenant/w/$workspace", props: {} }],
    },
  });
});

test("turned off, it says no, and nothing more is sent", async () => {
  const relay: Relay = { given: true, deletes: true, events: [], answers: [] };
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, {
    readers: { analytics: true },
  });
  await screen.getByRole("button", { name: /^Account/ }).click();
  const share = screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" });
  await expect.element(share).toHaveAttribute("aria-checked", "true");
  await share.click();
  await expect.poll(() => relay.answers).toEqual([false]);
  await expect
    .element(screen.getByRole("status").filter({ hasText: "Sharing how you use the app is off." }))
    .toBeInTheDocument();
});

test("a no whose deletion isn't done yet says so, in the menu and to a screen reader", async () => {
  const relay: Relay = { given: true, deletes: false, events: [], answers: [] };
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, {
    readers: { analytics: true },
  });
  await screen.getByRole("button", { name: /^Account/ }).click();
  await screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }).click();
  await expect
    .element(
      screen.getByRole("status").filter({
        hasText: "Sharing is off. What you shared is still being deleted, and will be.",
      }),
    )
    .toBeInTheDocument();
  await screen.getByRole("button", { name: /^Account/ }).click();
  await expect
    .element(screen.getByText("What you shared is still being deleted, and will be."))
    .toBeVisible();
  await expect
    .element(screen.getByRole("menuitem", { name: "What is shared, and how it is kept" }))
    .toHaveAttribute("href", expect.stringContaining("/portalr/guides/privacy/"));
});
