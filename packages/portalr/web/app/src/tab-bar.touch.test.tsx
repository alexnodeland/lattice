/**
 * On a phone, a narrow window with a finger for a pointer, the workspace's areas are a tab bar
 * along the window's foot, with the magnifier at its end, whose search takes the whole bar's
 * place; the Threads page starts a thread from its title's New; a thread's page has no tab bar,
 * its composer and what it asks hold the foot, and its way back is at the top (portalr ADR-0087).
 */

import { afterEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { open } from "./test/app";
import { APPROVAL, serve as notes, WORLD } from "./test/notes";

afterEach(() => {
  vi.unstubAllGlobals();
});

const at = (seq: number, event: unknown) => ({
  type: "event",
  seq,
  id: `evt_${seq}`,
  ts: "2026-10-27T09:00:00Z",
  workspace_id: "notes",
  actor: { kind: "user", id: "alice" },
  event,
});
const LOG = Array.from({ length: 12 }, (_, n) =>
  at(n + 1, { type: "thread_created", thread_id: `thr_${n}`, title: `Thread ${n}` }),
);
const serve = async (_request: Request, path: string) =>
  path.startsWith("/grantr/v1/tenants/acme/") ? Response.json([]) : undefined;
const tabBar = () => document.querySelector("[data-tab-bar]") as HTMLElement;
const visible = (element: Element | null) =>
  element instanceof HTMLElement && element.checkVisibility();

for (const width of [320, 375, 390, 430]) {
  test(`at ${width}px the areas are a tab bar at the foot, the current one marked, and the last thread sits above it`, async () => {
    await page.viewport(width, 667);
    const { screen } = await open("/t/acme/w/notes", serve, () => null, { artifactrLog: LOG });
    await expect.poll(() => visible(tabBar())).toBe(true);
    const bar = tabBar();
    const threads = [...bar.querySelectorAll("a")].find((a) => a.textContent?.includes("Threads"));
    expect(threads?.getAttribute("aria-current")).toBe("page");
    expect(bar.querySelector('nav[aria-label="Workspace"]')).not.toBeNull();
    // The areas' row at the page's top is gone, and so is the old band.
    expect([...document.querySelectorAll('main nav[aria-label="Workspace"]')].some(visible)).toBe(
      false,
    );
    expect(screen.getByRole("button", { name: "Search or go to…" }).query()).toBeNull();
    window.scrollTo(0, document.documentElement.scrollHeight);
    await expect
      .poll(
        () =>
          screen.getByRole("link", { name: "Thread 0" }).element().getBoundingClientRect().bottom <=
          bar.getBoundingClientRect().top,
      )
      .toBe(true);
    for (const target of bar.querySelectorAll("a, button")) {
      const box = target.getBoundingClientRect();
      expect(box.height).toBeGreaterThanOrEqual(44);
      expect(box.width).toBeGreaterThanOrEqual(44);
    }
  });
}

test("the title's New starts a thread: the composer opens, its words take the focus", async () => {
  await page.viewport(375, 667);
  const { screen } = await open("/t/acme/w/notes", serve, () => null, { artifactrLog: LOG });
  expect(screen.getByRole("textbox", { name: "Message" }).query()).toBeNull();
  const start = screen.getByRole("button", { name: "New thread" });
  await expect.element(start).toBeVisible();
  // The title keeps its whole word, on the button's line.
  const title = screen.getByRole("heading", { level: 1, name: "Threads" }).element();
  expect(title.getBoundingClientRect().height).toBeLessThan(48);
  await start.click();
  await expect.element(screen.getByRole("textbox", { name: "Message" })).toHaveFocus();
});

test("the magnifier turns the bar into the search; Close and Escape give the bar back, and the focus to it", async () => {
  await page.viewport(375, 667);
  const { screen, router } = await open("/t/acme/w/notes", serve, () => null, {
    artifactrLog: LOG,
  });
  await expect.poll(() => visible(tabBar())).toBe(true);
  const magnifier = tabBar().querySelector('button[aria-label="Search"]') as HTMLElement;
  for (const leave of ["Close", "Escape"] as const) {
    magnifier.click();
    const field = screen.getByRole("combobox", { name: "Search or go to" });
    await expect.element(field).toHaveFocus();
    // The search holds the window's foot, where the bar was.
    const popup = field.element().closest("[data-docked]") as HTMLElement;
    expect(Math.round(popup.getBoundingClientRect().bottom)).toBe(window.innerHeight);
    if (leave === "Close") {
      await screen.getByRole("button", { name: "Close" }).click();
    } else {
      await userEvent.keyboard("{Escape}");
    }
    await expect.element(screen.getByRole("combobox")).not.toBeInTheDocument();
    await expect.poll(() => document.activeElement).toBe(magnifier);
  }
  magnifier.click();
  await screen.getByRole("combobox", { name: "Search or go to" }).fill("Thread 3");
  await screen.getByRole("option", { name: "Thread 3" }).click();
  await expect.poll(() => router.state.location.pathname).toBe("/t/acme/w/notes/threads/thr_3");
});

test("a thread's page has no tab bar: its approval holds the foot, uncovered, and its way back is at the top", async () => {
  await page.viewport(375, 667);
  const { screen } = await open(
    "/t/acme/w/notes/threads/thr_1",
    notes,
    () => null,
    APPROVAL(undefined),
  );
  const approve = screen.getByRole("button", { name: "Approve" });
  await expect.element(approve).toBeInTheDocument();
  expect(tabBar()).toBeNull();
  await expect
    .element(screen.getByRole("banner").getByRole("link", { name: "All threads" }))
    .toBeVisible();
  window.scrollTo(0, 0);
  await expect
    .poll(() => {
      const box = approve.element().getBoundingClientRect();
      const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      return box.bottom <= window.innerHeight && approve.element().contains(hit);
    })
    .toBe(true);
});

test("with the keyboard up, the bar gives way, and nothing of it covers the field", async () => {
  await page.viewport(375, 667);
  await open("/t/acme/w/notes", serve, () => null, { artifactrLog: LOG });
  await expect.poll(() => visible(tabBar())).toBe(true);
  document.documentElement.dataset.keyboard = "";
  try {
    expect(getComputedStyle(tabBar()).display).toBe("none");
  } finally {
    delete document.documentElement.dataset.keyboard;
  }
});

const real = window.visualViewport;

test("the docked search sits on the on-screen keyboard, its field never under it", async () => {
  await page.viewport(375, 667);
  const viewport = new EventTarget() as EventTarget & { height: number; offsetTop: number };
  viewport.height = window.innerHeight;
  viewport.offsetTop = 0;
  Object.defineProperty(window, "visualViewport", { value: viewport, configurable: true });
  try {
    const { screen } = await open("/t/acme/w/notes/artifacts", serve, () => null, {
      artifactrLog: LOG,
    });
    await expect.poll(() => visible(tabBar())).toBe(true);
    (tabBar().querySelector('button[aria-label="Search"]') as HTMLElement).click();
    const field = screen.getByRole("combobox", { name: "Search or go to" });
    await expect.element(field).toHaveFocus();
    viewport.height = window.innerHeight - 300;
    viewport.dispatchEvent(new Event("resize"));
    const popup = field.element().closest("[data-docked]") as HTMLElement;
    await expect
      .poll(() => Math.round(popup.getBoundingClientRect().bottom))
      .toBe(window.innerHeight - 300);
    expect(field.element().getBoundingClientRect().bottom).toBeLessThanOrEqual(
      window.innerHeight - 300,
    );
  } finally {
    Object.defineProperty(window, "visualViewport", { value: real, configurable: true });
  }
});

test("writing a thread from New, the bar gives way and the composer holds the foot", async () => {
  await page.viewport(375, 667);
  const { screen } = await open("/t/acme/w/notes", serve, () => null, { artifactrLog: LOG });
  await expect.poll(() => visible(tabBar())).toBe(true);
  await screen.getByRole("button", { name: "New thread" }).click();
  const box = screen.getByRole("textbox", { name: "Message" });
  await expect.element(box).toHaveFocus();
  expect(getComputedStyle(tabBar()).display).toBe("none");
  const hit = box.element().getBoundingClientRect();
  expect(box.element().contains(document.elementFromPoint(hit.left + 20, hit.top + 10))).toBe(true);
});

test("on a phone what waits is in the top bar, and its link opens the threads that wait", async () => {
  await page.viewport(375, 667);
  const { screen, router } = await open("/t/acme/w/notes", notes, () => null, WORLD);
  const waiting = screen.getByRole("banner").getByRole("link", { name: /need/ });
  await expect.element(waiting).toBeVisible();
  await waiting.click();
  await expect.poll(() => router.state.location.search).toEqual({ show: "needs" });
  await expect.element(screen.getByRole("radio", { name: /^Needs you/ })).toBeChecked();
});

test("docked, the search's empty field shows the connected apps that are on, under the areas, each a finger's size (portalr ADR-0088)", async () => {
  await page.viewport(375, 667);
  const { screen } = await open(
    "/t/acme/w/notes",
    async (request, path) =>
      path === "/grantr/v1/tenants/acme/workspaces/notes/enabled-integrations"
        ? Response.json({ "tracker:plane": true })
        : serve(request, path),
    () => null,
    { artifactrLog: LOG, links: { "tracker:plane": "http://127.0.0.1:8090/" } },
  );
  await expect.poll(() => visible(tabBar())).toBe(true);
  (tabBar().querySelector('button[aria-label="Search"]') as HTMLElement).click();
  const apps = screen.getByRole("group", { name: "Connected apps" });
  await expect.element(apps).toBeVisible();
  const groups = [...document.querySelectorAll('[role="listbox"] fieldset')];
  expect(groups.indexOf(apps.element() as HTMLFieldSetElement)).toBeGreaterThan(
    groups.indexOf(screen.getByRole("group", { name: "Go to" }).element() as HTMLFieldSetElement),
  );
  const plane = apps.getByRole("option", { name: /^Open Plane.*opens in a new tab$/ });
  await expect.element(plane).toBeVisible();
  expect(plane.element().getBoundingClientRect().height).toBeGreaterThanOrEqual(36);
});
