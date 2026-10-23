/**
 * A native file's page while the native files' add-on loads (portalr ADR-0044): the file's
 * section says so, and the rest of the page is there.
 */

import { afterEach, expect, test, vi } from "vitest";
import { open } from "./test/app";
import { AT, FILE, REVISIONS, status } from "./test/files";

// Every add-on is still loading, as `useLoaded` says until its chunk arrives.
vi.mock(import("@portalr/ui"), async (original) => ({
  ...(await original()),
  useLoaded: () => ({ module: null, failed: false, error: null }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("a native file's section says it is loading until its add-on has", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/doc_1", async (_request, path) => {
    switch (path) {
      case `${AT}/artifacts/doc_1/revisions`:
        return Response.json(REVISIONS);
      case FILE:
        return Response.json(status(null, true));
      case "/grantr/v1/checks":
        return Response.json([false]);
      default:
        return undefined;
    }
  });
  await expect.element(screen.getByRole("heading", { name: "brief.docx" })).toBeVisible();
  await expect.element(screen.getByText("Loading the file…")).toBeVisible();
});
