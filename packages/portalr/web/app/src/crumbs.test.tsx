/**
 * Every page with a breadcrumb names the places above it as links, never as the page shown: a
 * router's fuzzy match would mark the parent `aria-current="page"` (ADR-0059).
 */

import { afterEach, expect, test, vi } from "vitest";
import type { RenderResult } from "vitest-browser-react";
import { open } from "./test/app";
import { AT } from "./test/files";

afterEach(() => {
  vi.unstubAllGlobals();
});

/** grantr allowing everything, and the reads each page needs. */
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
        kind: "dashboard",
        data: { title: "Spend", as_of: "2026-10-22T00:00:00Z", panels: [] },
        archived: false,
        actor: { kind: "user", id: "alice" },
      },
    ]);
  }
  if (path.endsWith("/rules/tidy")) {
    // As text: a rule's `then` is its action, which an object literal can't name safely.
    const rule = '{"name":"tidy","when":{"filter":{}},"then":{"action":"notify"}}';
    return new Response(`{"origin":"code","version":null,"rule":${rule}}`, {
      headers: { "content-type": "application/json" },
    });
  }
  return path.startsWith("/grantr/v1/tenants/acme/") ? Response.json([]) : undefined;
};

async function crumbsOf(screen: RenderResult) {
  const trail = screen.getByRole("navigation", { name: "Breadcrumb" });
  await expect.element(trail.getByRole("link").first()).toBeVisible();
  return trail
    .getByRole("link")
    .elements()
    .map((crumb) => [crumb.textContent, crumb.getAttribute("aria-current")]);
}

test("an artifact's crumbs are links, none the page shown", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/note_1", serve);
  for (const [, current] of await crumbsOf(screen)) {
    expect(current).toBeNull();
  }
});

test("a rule's crumbs are links, none the page shown", async () => {
  const { screen } = await open("/t/acme/w/notes/rules/tidy", serve);
  for (const [, current] of await crumbsOf(screen)) {
    expect(current).toBeNull();
  }
});

test("an artifact marks itself, with its files and mini apps, to be blocked whole from a session replay", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/note_1", serve);
  const trail = screen.getByRole("navigation", { name: "Breadcrumb" });
  await expect.element(trail.getByRole("link").first()).toBeVisible();
  expect(trail.element().closest('[data-portalr-replay="block"]')).not.toBeNull();
});
