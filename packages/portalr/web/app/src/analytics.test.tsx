/**
 * Product analytics in the app (lattice RFC-0008): off until the person turns it on in the account
 * menu, and then each page they open, by the router's name for its route, in their tenant.
 */

import { afterEach, expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { routeOf } from "./analytics";
import { open } from "./test/app";
import { FLAGS } from "./test/files";

interface Relay {
  given: boolean;
  /** Whether a deletion a no asked for isn't done yet, as the relay reads it. */
  deleting: boolean;
  /** Whether the relay takes an answer: false answers 503. */
  up: boolean;
  /** Whether the relay can be read: false answers 503. */
  readable: boolean;
  readonly events: { tenant: string | null; body: unknown }[];
  readonly answers: boolean[];
}

const relayOf = (given: boolean): Relay => ({
  given,
  deleting: false,
  up: true,
  readable: true,
  events: [],
  answers: [],
});

const DELETING =
  "Deleting what you shared hasn't finished yet. It will be retried until it is done.";

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
        if (!relay.up) {
          return Response.json({ detail: "down" }, { status: 503 });
        }
        relay.given = ((await request.json()) as { given: boolean }).given;
        relay.answers.push(relay.given);
        return Response.json({
          given: relay.given,
          deleted: relay.given ? null : !relay.deleting,
        });
      }
      if (!relay.readable) {
        return Response.json({ detail: "down" }, { status: 503 });
      }
      return Response.json({ given: relay.given, deleting: relay.deleting });
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

async function openMenu(screen: Awaited<ReturnType<typeof open>>["screen"]) {
  // Closed first, whether or not a click left it open, then opened.
  await userEvent.keyboard("{Escape}");
  await screen.getByRole("button", { name: /^Account/ }).click();
  await expect.element(screen.getByRole("menu")).toBeVisible();
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
  const relay = relayOf(true);
  const { screen, fetched } = await open("/t/acme/w/notes", serving(relay));
  await openMenu(screen);
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

test("with the switch shown and off, nothing is sent", async () => {
  const relay = relayOf(false);
  const { screen, fetched } = await open("/t/acme/w/notes", serving(relay), undefined, {
    readers: { analytics: true },
  });
  await openMenu(screen);
  await expect
    .element(screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }))
    .toHaveAttribute("aria-checked", "false");
  await new Promise((resolve) => setTimeout(resolve, 300));
  const asked = fetched.mock.calls.map(([input]) => String(input));
  expect(asked.some((url) => /analytics\/session|\/events/.test(url))).toBe(false);
  expect(relay.events).toEqual([]);
});

test("off until turned on, then the page the person is on is sent, by its route, in the tenant", async () => {
  const relay = relayOf(false);
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, {
    readers: { analytics: true },
  });
  await openMenu(screen);
  await screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }).click();
  await expect.poll(() => relay.answers).toEqual([true]);
  await expect.poll(() => relay.events.length, { timeout: 10_000 }).toBe(1);
  expect(relay.events[0]).toEqual({
    tenant: "acme",
    body: {
      session: "signed",
      events: [{ event: "app.page.viewed.v1", route: "/t/$tenant/w/$workspace" }],
    },
  });
});

test("after a no, what waited is dropped and nothing more is sent", async () => {
  const relay = relayOf(true);
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, {
    readers: { analytics: true },
  });
  await openMenu(screen);
  await screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }).click();
  await expect.poll(() => relay.answers).toEqual([false]);
  await expect
    .element(screen.getByRole("status").filter({ hasText: "Sharing how you use the app is off." }))
    .toBeInTheDocument();
  // Past the five seconds a page view would wait: it was dropped with the no.
  await new Promise((resolve) => setTimeout(resolve, 5_500));
  expect(relay.events).toEqual([]);
});

test("a no whose deletion isn't done yet says so, to a screen reader as it happens", async () => {
  const relay = relayOf(true);
  relay.deleting = true;
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, {
    readers: { analytics: true },
  });
  await openMenu(screen);
  await screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }).click();
  await expect
    .element(screen.getByRole("status").filter({ hasText: `Sharing is off. ${DELETING}` }))
    .toBeInTheDocument();
});

test("a deletion still owed is read from the relay, as a reload reads it, and shown in the menu", async () => {
  const relay = relayOf(false);
  relay.deleting = true;
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, {
    readers: { analytics: true },
  });
  await openMenu(screen);
  await expect.element(screen.getByText(DELETING)).toBeVisible();
  await expect
    .element(
      screen.getByRole("menuitem", {
        name: "What is shared, and how it is kept (opens in a new tab)",
      }),
    )
    .toHaveAttribute("href", expect.stringContaining("/portalr/guides/privacy/"));
});

test("an answer the relay doesn't take puts the switch back, and says so", async () => {
  const relay = relayOf(true);
  relay.up = false;
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, {
    readers: { analytics: true },
  });
  await openMenu(screen);
  await screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }).click();
  await expect
    .element(
      screen.getByRole("status").filter({
        hasText:
          "Your answer wasn't saved, so nothing has changed. Try again. Sharing how you use the app is on.",
      }),
    )
    .toBeInTheDocument();
  await expect
    .element(screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }))
    .toHaveAttribute("aria-checked", "true");
});

const CONSENT = ["portalr", "analytics", "consent", "alice"];

test("a read that fails while a deletion is owed keeps the note, and the reading again", async () => {
  const relay = relayOf(false);
  relay.deleting = true;
  const { screen, queryClient } = await open("/t/acme/w/notes", serving(relay), undefined, {
    readers: { analytics: true },
  });
  await openMenu(screen);
  await expect.element(screen.getByText(DELETING)).toBeVisible();
  relay.readable = false;
  await queryClient.refetchQueries({ queryKey: CONSENT }).catch(() => undefined);
  // The last answer read stands: still owed, so the account menu still reads it again.
  expect(queryClient.getQueryData(CONSENT)).toEqual({ given: false, deleting: true });
  await expect.element(screen.getByText(DELETING)).toBeVisible();
});

test("an answer not saved, and a relay that can't be read after, keeps the switch as it was", async () => {
  const relay = relayOf(true);
  const { screen, queryClient } = await open("/t/acme/w/notes", serving(relay), undefined, {
    readers: { analytics: true },
  });
  await openMenu(screen);
  await expect
    .element(screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }))
    .toHaveAttribute("aria-checked", "true");
  relay.up = false;
  relay.readable = false;
  await screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }).click();
  await expect
    .element(
      screen
        .getByRole("status")
        .filter({ hasText: "Your answer wasn't saved, so nothing has changed." }),
    )
    .toBeInTheDocument();
  await new Promise((resolve) => setTimeout(resolve, 500));
  expect(queryClient.getQueryData(CONSENT)).toEqual({ given: true, deleting: false });
});

test("a yes keeps a deletion still owed in view until the relay has done it", async () => {
  const relay = relayOf(false);
  relay.deleting = true;
  const { screen, queryClient } = await open("/t/acme/w/notes", serving(relay), undefined, {
    readers: { analytics: true },
  });
  await openMenu(screen);
  await expect.element(screen.getByText(DELETING)).toBeVisible();
  relay.readable = false;
  await screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }).click();
  await expect.poll(() => relay.answers).toEqual([true]);
  expect(queryClient.getQueryData(CONSENT)).toEqual({ given: true, deleting: true });
});
