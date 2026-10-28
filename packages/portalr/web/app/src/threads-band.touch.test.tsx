/**
 * On a phone, a narrow window with a finger for a pointer, the threads page's foot is a band of
 * the search and New thread, never the composer over the list; and the last thread, scrolled to,
 * sits above the band, uncovered (portalr ADR-0087).
 */

import { afterEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open } from "./test/app";

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

for (const width of [320, 393, 430, 768]) {
  test(`at ${width}px the foot is the band, and the last thread sits above it`, async () => {
    await page.viewport(width, 700);
    const { screen } = await open("/t/acme/w/notes", serve, () => null, { artifactrLog: LOG });
    const band = screen.getByRole("button", { name: "Search or go to…" });
    await expect.element(band).toBeVisible();
    await expect.element(screen.getByRole("button", { name: "New thread" })).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Message" }).query()).toBeNull();
    window.scrollTo(0, document.documentElement.scrollHeight);
    const last = screen.getByRole("link", { name: "Thread 0" }).element().getBoundingClientRect();
    const foot = band.element().getBoundingClientRect();
    expect(last.bottom).toBeLessThanOrEqual(foot.top);
    await screen.getByRole("button", { name: "New thread" }).click();
    await expect.element(screen.getByRole("textbox", { name: "Message" })).toHaveFocus();
  });
}
