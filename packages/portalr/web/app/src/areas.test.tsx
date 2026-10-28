/**
 * A page inside an area, an artifact's, a rule's or a thread's, has no breadcrumb: the bar's
 * areas mark the one it is in, the way back up (portalr ADR-0087).
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

/** The area the bar marks as where the page is, and the page's breadcrumbs, if any. */
async function marked(screen: RenderResult, area: string) {
  const link = screen
    .getByRole("navigation", { name: "Workspace" })
    .first()
    .getByRole("link", { name: area });
  await expect.element(link).toHaveAttribute("aria-current");
  expect(screen.getByRole("navigation", { name: "Breadcrumb" }).elements()).toHaveLength(0);
}

test("an artifact's page is marked in Artifacts, with no breadcrumb", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/note_1", serve);
  await marked(screen, "Artifacts");
});

test("a rule's page is marked in Rules, with no breadcrumb", async () => {
  const { screen } = await open("/t/acme/w/notes/rules/tidy", serve);
  await marked(screen, "Rules");
});

test("an artifact marks itself, with its files and mini apps, to be blocked whole from a session replay", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/note_1", serve);
  const heading = screen.getByRole("heading", { level: 1 });
  await expect.element(heading).toBeVisible();
  expect(heading.element().closest('[data-portalr-replay="block"]')).not.toBeNull();
});
