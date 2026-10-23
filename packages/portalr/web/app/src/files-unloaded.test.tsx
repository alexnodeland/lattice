/**
 * A native file's page where the native files' add-on won't load (portalr ADR-0044): the rest of
 * the page stands, the file's section says why in the kit's words, once however many revisions
 * changed its words, and offers to try again; and the file's status was read as the add-on
 * loaded, not after.
 */

import { afterEach, expect, test, vi } from "vitest";
import { open } from "./test/app";
import { AT, FILE, manifest, status } from "./test/files";

// Every add-on fails to load, as `useLoaded` says once a browser refuses a chunk it can't fetch;
// that it does is ui's `on-demand.test.ts`'s.
vi.mock(import("@portalr/ui"), async (original) => ({
  ...(await original()),
  useLoaded: () => ({
    module: null,
    failed: true,
    error: new TypeError("Failed to fetch dynamically imported module"),
  }),
}));

/** Four revisions, each of whose words differ from the one before: three that changed them. */
const CHANGED = ["a", "b", "c", "d"].map((text, index) => ({
  artifact_id: "doc_1",
  version: index + 1,
  kind: "word_document",
  data: manifest(text, "Brief", 2),
  archived: false,
  actor: { kind: "user", id: "alice" },
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("a native file whose add-on won't load says why, and the page stands", async () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  const { screen, fetched } = await open(
    "/t/acme/w/notes/artifacts/doc_1",
    async (_request, path) => {
      switch (path) {
        case `${AT}/artifacts/doc_1/revisions`:
          return Response.json(CHANGED);
        case FILE:
          return Response.json(status(null, true));
        case "/grantr/v1/checks":
          return Response.json([false]);
        default:
          return undefined;
      }
    },
  );
  await expect.element(screen.getByRole("heading", { name: "brief.docx" })).toBeVisible();
  // The file's section says so, once; the revisions whose words changed say nothing.
  await expect.element(screen.getByText(/^Something went wrong\./)).toBeVisible();
  expect(screen.getByRole("alert").elements()).toHaveLength(1);
  await expect.element(screen.getByRole("button", { name: "Try again" })).toBeVisible();
  const read = fetched.mock.calls.map(([input]) => new URL((input as Request).url).pathname);
  expect(read).toContain(FILE);
});
