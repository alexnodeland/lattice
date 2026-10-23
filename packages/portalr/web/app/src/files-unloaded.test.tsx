/**
 * A native file's page where the native files' add-on won't load (portalr ADR-0044): the rest of
 * the page stands, the file's section says why in the kit's words, and the file's status was read
 * as the add-on loaded, not after.
 */

import { afterEach, expect, test, vi } from "vitest";
import { open } from "./test/app";
import { AT, FILE, REVISIONS, status } from "./test/files";

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
          return Response.json(REVISIONS);
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
  // The file's section, and the revision whose words changed, each say so.
  const said = screen.getByText(/^Something went wrong\./);
  await expect.poll(() => said.elements()).toHaveLength(2);
  const read = fetched.mock.calls.map(([input]) => new URL((input as Request).url).pathname);
  expect(read).toContain(FILE);
});
