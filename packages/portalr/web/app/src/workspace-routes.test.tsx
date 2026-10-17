/**
 * A workspace as a route, over a stubbed grantr and artifactr stream: it opens without waiting on
 * its integrations when grantr fails them, reads them once, and again when a command is refused
 * as `not_enabled` (portalr ADR-0045).
 */

import { afterEach, expect, test, vi } from "vitest";
import { open } from "./test/app";

const FLAGS = "/grantr/v1/tenants/acme/workspaces/notes/enabled-integrations";

/** How often the page asked grantr for the workspace's integrations. */
const reads = (fetched: { mock: { calls: unknown[][] } }) =>
  fetched.mock.calls.filter(([input]) => new URL((input as Request).url).pathname === FLAGS).length;

afterEach(() => {
  vi.unstubAllGlobals();
});

test("with grantr failing, the workspace opens at once, and its integrations are read once", async () => {
  const started = performance.now();
  const { screen, fetched } = await open("/t/acme/w/notes", async (_request, path) =>
    path === FLAGS ? new Response("upstream gone", { status: 503 }) : undefined,
  );
  await expect.element(screen.getByRole("heading", { name: "Threads" })).toBeVisible();
  expect(performance.now() - started).toBeLessThan(1500);
  // The app's query client tries a failed read again after a second: this one isn't.
  await new Promise((waited) => setTimeout(waited, 1500));
  expect(reads(fetched)).toBe(1);
});

test("a command refused as not_enabled reads the workspace's integrations again", async () => {
  const { screen, fetched } = await open(
    "/t/acme/w/notes",
    async (_request, path) => (path === FLAGS ? Response.json({ excalidraw: false }) : undefined),
    (command) => (command.type === "create_thread" ? "not_enabled" : null),
  );
  await expect.poll(() => reads(fetched)).toBe(1);
  await screen.getByRole("textbox", { name: "New thread" }).fill("Sketch");
  await screen.getByRole("button", { name: "Start" }).click();
  await expect
    .element(screen.getByText("The thread wasn't started: the server refused it."))
    .toBeVisible();
  await expect.poll(() => reads(fetched)).toBe(2);
});
