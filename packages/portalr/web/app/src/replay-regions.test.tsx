/**
 * What the recorder blocks, held to the app's own pages (portalr ADR-0077): `main` is blocked
 * unless a page marks itself `allow`, so a page that says nothing, a new one, or a not-found page
 * that echoes an address is not recorded; and the nav drawer is still recorded while the dialogs
 * that hold who has access are not.
 */

import { afterEach, expect, test, vi } from "vitest";
import routes from "../../../src/portalr/analytics/routes.json";
import { BLOCKED } from "./on-demand/replay";
import { open } from "./test/app";
import { AT } from "./test/files";

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Every route the app has, with a concrete address, and whether it may be recorded. */
const PAGES: Record<string, { at: string; allowed: boolean }> = {
  "/": { at: "/", allowed: false },
  "/sign-in": { at: "/sign-in", allowed: false },
  "/t/$tenant": { at: "/t/acme", allowed: false },
  "/t/$tenant/$": { at: "/t/acme/nothing-here", allowed: false },
  "/t/$tenant/w/$workspace": { at: "/t/acme/w/notes", allowed: false },
  "/t/$tenant/w/$workspace/$": { at: "/t/acme/w/notes/nothing-here", allowed: false },
  "/t/$tenant/w/$workspace/artifacts": { at: "/t/acme/w/notes/artifacts", allowed: false },
  "/t/$tenant/w/$workspace/artifacts/$artifact": {
    at: "/t/acme/w/notes/artifacts/note_1",
    allowed: false,
  },
  "/t/$tenant/w/$workspace/proposals": { at: "/t/acme/w/notes/proposals", allowed: false },
  "/t/$tenant/w/$workspace/rules": { at: "/t/acme/w/notes/rules", allowed: false },
  "/t/$tenant/w/$workspace/rules/$rule": { at: "/t/acme/w/notes/rules/tidy", allowed: false },
  "/t/$tenant/w/$workspace/runs": { at: "/t/acme/w/notes/runs", allowed: true },
  "/t/$tenant/w/$workspace/threads/$thread": {
    at: "/t/acme/w/notes/threads/thr_1",
    allowed: false,
  },
};

const serve = async (request: Request, path: string) => {
  if (path === "/grantr/v1/checks") {
    const asked: unknown[] = await request.json();
    return Response.json(asked.map(() => true));
  }
  if (path === `${AT}/artifacts/note_1/revisions`) {
    return Response.json([
      {
        artifact_id: "note_1",
        version: 1,
        kind: "note",
        data: { title: "Plan" },
        archived: false,
        actor: { kind: "user", id: "alice" },
      },
    ]);
  }
  return path.startsWith("/grantr/v1/tenants/acme/") ? Response.json([]) : undefined;
};

test("the table names every route the app has, and no other", () => {
  expect(Object.keys(PAGES).sort()).toEqual([...routes.routes].sort());
});

test.each(Object.entries(PAGES))("%s: main is %s", async (_route, { at, allowed }) => {
  await open(at, serve);
  await expect.poll(() => document.querySelector("main") !== null, { timeout: 5_000 }).toBe(true);
  await expect
    .poll(() => document.querySelector("main")?.matches(BLOCKED), { timeout: 5_000 })
    .toBe(!allowed);
  if (allowed) {
    expect(document.querySelector('main > div > [data-portalr-replay="allow"]')).not.toBeNull();
  }
  // No chat, file, markdown or free-text surface is drawn where the recorder would see it.
  const surfaces =
    '[role="log"], textarea, iframe, canvas, [data-composer-dock], [data-streamdown]';
  for (const surface of document.querySelectorAll(surfaces)) {
    expect(surface.closest(BLOCKED), surface.outerHTML.slice(0, 80)).not.toBeNull();
  }
});

test("the nav drawer is recorded, and a dialog that holds who has access is not", async () => {
  const { screen } = await open("/t/acme/w/notes", serve);
  await screen.getByRole("button", { name: "Menu" }).click();
  const drawer = screen.getByRole("dialog").element();
  expect(drawer.querySelector("[data-drawer]")).not.toBeNull();
  expect(drawer.matches(BLOCKED)).toBe(false);
  const sharing = document.createElement("div");
  sharing.setAttribute("role", "dialog");
  document.body.append(sharing);
  expect(sharing.matches(BLOCKED)).toBe(true);
  sharing.remove();
});
