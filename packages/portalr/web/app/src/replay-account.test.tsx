/**
 * Session replay in the app (lattice RFC-0008, portalr ADR-0077): off until the person has said
 * yes to analytics and then to replay, in the account menu; and then the layout of the page they
 * are on, with no word or address of it, to the relay, in their tenant.
 */

import { afterEach, expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { BLOCKED } from "./on-demand/replay";
import { open } from "./test/app";
import { FLAGS } from "./test/files";
import { unmasked } from "./test/unmasked";

interface Relay {
  analytics: boolean;
  replay: boolean;
  /** Whether a deletion of recordings isn't done yet, as the relay reads it. */
  deleting: boolean;
  /** Whether the relay takes an answer to replay: false answers 503. */
  up: boolean;
  readonly replayed: {
    tenant: string | null;
    body: { session: string; events: unknown[] };
    bytes: number;
  }[];
  readonly replayAnswers: boolean[];
  /** Whether replay's answer can be read: false answers 503. */
  replayReadable: boolean;
  /** Whether the relay records none of a batch, as where the person's yes is gone. */
  refuses: boolean;
  readonly asked: string[];
}

const relayOf = (analytics: boolean, replay: boolean): Relay => ({
  analytics,
  replay,
  deleting: false,
  up: true,
  replayed: [],
  replayAnswers: [],
  refuses: false,
  replayReadable: true,
  asked: [],
});

const MENU = /^Account/;
const SWITCH = "Record my sessions to improve the app";
const ABOUT =
  "Records the layout of the pages you visit and where you click. All text and anything you type is hidden, and chats, files, mini apps and Access are never recorded. Turning it off deletes your recordings.";
const LINK = "How recording works (opens in a new tab)";
const PENDING =
  "Deleting your recordings hasn't finished yet. It will be retried until it is done.";
const NOT_SAVED = "Your answer wasn't saved, so nothing has changed. Try again.";

function serving(relay: Relay) {
  return async (request: Request, path: string) => {
    relay.asked.push(`${request.method} ${path}`);
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
        relay.analytics = ((await request.json()) as { given: boolean }).given;
        if (!relay.analytics) {
          // The relay withdraws replay with analytics.
          relay.replay = false;
        }
        return Response.json({ given: relay.analytics, deleted: relay.analytics ? null : true });
      }
      return Response.json({ given: relay.analytics, deleting: false });
    }
    if (path === "/portalr/v1/analytics/replay/consent") {
      if (request.method === "PUT") {
        if (!relay.up) {
          return Response.json({ detail: "down" }, { status: 503 });
        }
        relay.replay = ((await request.json()) as { given: boolean }).given;
        relay.replayAnswers.push(relay.replay);
        return Response.json({ given: relay.replay, deleted: relay.replay ? null : true });
      }
      if (!relay.replayReadable) {
        return Response.json({ detail: "down" }, { status: 503 });
      }
      return Response.json({ given: relay.replay, deleting: relay.deleting });
    }
    if (path === "/portalr/v1/analytics/session") {
      return Response.json({ session: "signed" });
    }
    if (path === "/portalr/v1/events") {
      return Response.json({ recorded: 1, dropped: 0 }, { status: 202 });
    }
    if (path === "/portalr/v1/analytics/replay") {
      const text = await request.text();
      relay.replayed.push({
        tenant: request.headers.get("x-tenant"),
        body: JSON.parse(text),
        bytes: new TextEncoder().encode(text).length,
      });
      return Response.json(
        { recorded: relay.refuses ? 0 : 1, dropped: relay.refuses ? 1 : 0 },
        { status: 202 },
      );
    }
    return undefined;
  };
}

const world = { readers: { analytics: true }, replay: true } as const;

async function openMenu(screen: Awaited<ReturnType<typeof open>>["screen"]) {
  await userEvent.keyboard("{Escape}");
  await screen.getByRole("button", { name: MENU }).click();
  await expect.element(screen.getByRole("menu")).toBeVisible();
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("where the deployment records no replays there is no switch, and nothing is asked of replay", async () => {
  const relay = relayOf(true, false);
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, {
    readers: { analytics: true },
  });
  await openMenu(screen);
  await expect
    .element(screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }))
    .toBeVisible();
  await new Promise((resolve) => setTimeout(resolve, 300));
  expect(screen.getByRole("menuitemcheckbox", { name: SWITCH }).elements()).toHaveLength(0);
  expect(relay.asked.filter((each) => each.includes("/analytics/replay"))).toEqual([]);
});

test("without a yes to analytics there is no switch to turn on, and nothing is recorded", async () => {
  const relay = relayOf(false, false);
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, world);
  await openMenu(screen);
  await expect
    .element(screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }))
    .toHaveAttribute("aria-checked", "false");
  await new Promise((resolve) => setTimeout(resolve, 300));
  expect(screen.getByRole("menuitemcheckbox", { name: SWITCH }).elements()).toHaveLength(0);
  expect(relay.replayed).toEqual([]);
});

test("off until turned on: the switch says what it records, and then the page is recorded with no word of it", async () => {
  const relay = relayOf(true, false);
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, world);
  await openMenu(screen);
  const item = screen.getByRole("menuitemcheckbox", { name: SWITCH });
  await expect.element(item).toHaveAttribute("aria-checked", "false");
  await expect.element(item).toHaveAccessibleDescription(ABOUT);
  await expect
    .element(screen.getByRole("menuitem", { name: LINK }))
    .toHaveAttribute("href", expect.stringContaining("/portalr/guides/privacy/#session-replay"));
  expect(
    relay.asked.filter((each) => each.includes("/analytics/replay/") && each.startsWith("POST")),
  ).toEqual([]);
  expect(relay.replayed).toEqual([]);
  await item.click();
  await expect.poll(() => relay.replayAnswers).toEqual([true]);
  await expect
    .element(screen.getByRole("status").filter({ hasText: "Recording your sessions is on." }))
    .toBeInTheDocument();
  await expect.poll(() => relay.replayed.length, { timeout: 15_000 }).toBeGreaterThan(0);
  const first = relay.replayed[0];
  expect(first?.tenant).toBe("acme");
  expect(first?.body.session).toBe("signed");
  const events = relay.replayed.flatMap((each) => each.body.events);
  expect(unmasked(events)).toBeNull();
  const json = JSON.stringify(events);
  for (const word of ["Threads", "Artifacts", "Proposals", "alice", "acme", "notes"]) {
    expect(json, word).not.toContain(word);
  }
  expect(json, "the layout is there").toContain('"tagName":"nav"');
  // The first batch holds the page and its styles, about 130 kB: well under the relay's 512 KiB.
  expect(first?.bytes).toBeLessThan(250_000);
});

test("a no stops the recording and nothing more is sent", async () => {
  const relay = relayOf(true, true);
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, world);
  await expect.poll(() => relay.replayed.length, { timeout: 15_000 }).toBeGreaterThan(0);
  await openMenu(screen);
  await screen.getByRole("menuitemcheckbox", { name: SWITCH }).click();
  await expect.poll(() => relay.replayAnswers).toEqual([false]);
  await expect
    .element(screen.getByRole("status").filter({ hasText: "Recording your sessions is off." }))
    .toBeInTheDocument();
  await new Promise((resolve) => setTimeout(resolve, 200));
  const sent = relay.replayed.length;
  await new Promise((resolve) => setTimeout(resolve, 5_500));
  expect(relay.replayed.length).toBe(sent);
});

test("a no to sharing is a no to recording too: the switch goes, and nothing more is sent", async () => {
  const relay = relayOf(true, true);
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, world);
  await expect.poll(() => relay.replayed.length, { timeout: 15_000 }).toBeGreaterThan(0);
  await openMenu(screen);
  await screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }).click();
  await expect
    .poll(() => screen.getByRole("menuitemcheckbox", { name: SWITCH }).elements().length)
    .toBe(0);
  await new Promise((resolve) => setTimeout(resolve, 200));
  const sent = relay.replayed.length;
  await new Promise((resolve) => setTimeout(resolve, 5_500));
  expect(relay.replayed.length).toBe(sent);
});

test("an answer the relay doesn't take puts the switch back, and says so, in words of the app's own", async () => {
  const relay = relayOf(true, false);
  relay.up = false;
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, world);
  await openMenu(screen);
  await screen.getByRole("menuitemcheckbox", { name: SWITCH }).click();
  await expect
    .element(
      screen
        .getByRole("status")
        .filter({ hasText: `${NOT_SAVED} Recording your sessions is off.` }),
    )
    .toBeInTheDocument();
  await expect
    .element(screen.getByRole("menuitemcheckbox", { name: SWITCH }))
    .toHaveAttribute("aria-checked", "false");
  expect(relay.replayed).toEqual([]);
});

test("a deletion of recordings still owed is said in the menu, and to a screen reader", async () => {
  const relay = relayOf(true, false);
  relay.deleting = true;
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, world);
  await openMenu(screen);
  await expect.element(screen.getByText(PENDING)).toBeVisible();
  await expect
    .element(
      screen.getByRole("status").filter({ hasText: `Recording your sessions is off. ${PENDING}` }),
    )
    .toBeInTheDocument();
});

test("analytics yes, replay yes, analytics no, analytics yes: the switch is off, and nothing is recorded or sent", async () => {
  const relay = relayOf(true, true);
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, world);
  await expect.poll(() => relay.replayed.length, { timeout: 15_000 }).toBeGreaterThan(0);
  await openMenu(screen);
  const sharing = screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" });
  await sharing.click();
  await expect.poll(() => relay.analytics).toBe(false);
  await expect
    .poll(() => screen.getByRole("menuitemcheckbox", { name: SWITCH }).elements().length)
    .toBe(0);
  await sharing.click();
  await expect.poll(() => relay.analytics).toBe(true);
  await expect
    .element(screen.getByRole("menuitemcheckbox", { name: SWITCH }))
    .toHaveAttribute("aria-checked", "false");
  const sent = relay.replayed.length;
  await new Promise((resolve) => setTimeout(resolve, 6_000));
  expect(relay.replayed.length, "none is sent on the earlier yes").toBe(sent);
  expect(relay.replayAnswers, "and no answer is made for the person").toEqual([]);
});

test("the recording starts on the relay's yes, not on the switch's: a yes it hasn't taken records nothing", async () => {
  const relay = relayOf(true, false);
  relay.up = false;
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, world);
  await openMenu(screen);
  await screen.getByRole("menuitemcheckbox", { name: SWITCH }).click();
  await expect
    .element(screen.getByRole("status").filter({ hasText: NOT_SAVED }))
    .toBeInTheDocument();
  await new Promise((resolve) => setTimeout(resolve, 6_000));
  expect(relay.replayed).toEqual([]);
});

test("a relay that records none of a batch stops the recording", async () => {
  const relay = relayOf(true, true);
  relay.refuses = true;
  await open("/t/acme/w/notes", serving(relay), undefined, world);
  await expect.poll(() => relay.replayed.length, { timeout: 15_000 }).toBe(1);
  await new Promise((resolve) => setTimeout(resolve, 6_000));
  expect(relay.replayed.length, "no second batch is sent").toBe(1);
});

test("a withdrawal made in another tab is seen when this one is focused again, and the recording stops", async () => {
  const relay = relayOf(true, true);
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, world);
  await expect.poll(() => relay.replayed.length, { timeout: 15_000 }).toBeGreaterThan(0);
  relay.replay = false;
  document.dispatchEvent(new Event("visibilitychange", { bubbles: true }));
  await openMenu(screen);
  await expect
    .element(screen.getByRole("menuitemcheckbox", { name: SWITCH }))
    .toHaveAttribute("aria-checked", "false");
  await new Promise((resolve) => setTimeout(resolve, 500));
  const sent = relay.replayed.length;
  await new Promise((resolve) => setTimeout(resolve, 5_500));
  expect(relay.replayed.length).toBe(sent);
});

test("a replay yes read before an analytics no is not believed after an analytics yes, even if replay can't be read", async () => {
  const relay = relayOf(true, true);
  const { screen } = await open("/t/acme/w/notes", serving(relay), undefined, world);
  await openMenu(screen);
  // The yes, read: what the switch and the recorder both start from. Not a first batch, which
  // waits the recorder's five seconds and spent a third of the test's time (#812).
  await expect
    .element(screen.getByRole("status").filter({ hasText: "Recording your sessions is on." }))
    .toBeInTheDocument();
  const sharing = screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" });
  relay.replayReadable = false;
  await sharing.click();
  await expect.poll(() => relay.analytics).toBe(false);
  await expect
    .element(screen.getByRole("status").filter({ hasText: "Recording your sessions is off." }))
    .toBeInTheDocument();
  const sent = relay.replayed.length;
  await sharing.click();
  await expect.poll(() => relay.analytics).toBe(true);
  // Longer than a recorder waits before its first batch: one started on the old yes would send.
  await new Promise((resolve) => setTimeout(resolve, 7_000));
  expect(relay.replayed.length, "no recorder starts on a yes that was read before").toBe(sent);
  expect(
    relay.asked.filter((each) => each === "GET /portalr/v1/analytics/replay/consent").length,
  ).toBeGreaterThan(1);
});

/** The events the relay was sent from `from` on, as text. */
const sentFrom = (relay: Relay, from: number) =>
  JSON.stringify(relay.replayed.slice(from).flatMap((each) => each.body.events));

test("the runs page, opened first, is recorded once it has read, though it suspended at the start", async () => {
  const relay = relayOf(true, true);
  await open("/t/acme/w/notes/runs", serving(relay), undefined, world);
  await expect
    .poll(() => sentFrom(relay, 0).includes('"data-portalr-replay":"allow"'), { timeout: 15_000 })
    .toBe(true);
});

test("the runs page, reached from one that is blocked, is recorded too", async () => {
  const relay = relayOf(true, true);
  const { router } = await open("/t/acme/w/notes", serving(relay), undefined, world);
  await expect.poll(() => relay.replayed.length, { timeout: 15_000 }).toBeGreaterThan(0);
  expect(sentFrom(relay, 0)).not.toContain('"data-portalr-replay":"allow"');
  await router.navigate({
    to: "/t/$tenant/w/$workspace/runs",
    params: { tenant: "acme", workspace: "notes" },
  });
  await expect
    .poll(() => sentFrom(relay, 0).includes('"data-portalr-replay":"allow"'), { timeout: 15_000 })
    .toBe(true);
});

test("leaving the runs page for a thread records nothing of the thread", async () => {
  const relay = relayOf(true, true);
  const { router } = await open("/t/acme/w/notes/runs", serving(relay), undefined, world);
  await expect
    .poll(() => sentFrom(relay, 0).includes('"data-portalr-replay":"allow"'), { timeout: 15_000 })
    .toBe(true);
  const before = relay.replayed.length;
  await router.navigate({
    to: "/t/$tenant/w/$workspace/threads/$thread",
    params: { tenant: "acme", workspace: "notes", thread: "thr_1" },
  });
  await expect
    .poll(() => document.querySelector("main")?.matches(BLOCKED), { timeout: 5_000 })
    .toBe(true);
  await new Promise((resolve) => setTimeout(resolve, 6_000));
  const after = sentFrom(relay, before);
  expect(after).not.toContain('"id":"thread"');
  expect(after).not.toContain('"role":"log"');
  expect(after).not.toContain("data-composer-dock");
});
