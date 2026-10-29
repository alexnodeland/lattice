/**
 * A check-out on a phone (portalr ADR-0049): a file whose app has no editor that opens in the
 * window says so plainly, beside the way it can still be edited.
 */

import { expect, test, vi } from "vitest";
import { open } from "./test/app";
import { AT, FILE, FLAGS, REVISIONS, status } from "./test/files";

const PAGE = "/t/acme/w/notes/artifacts/doc_1";

/** The file, held by no one, of an app whose build hands no file over. */
const serving = async (_request: Request, path: string) =>
  path === `${AT}/artifacts/doc_1/revisions`
    ? Response.json(REVISIONS)
    : path === FILE
      ? Response.json({ ...status(null), limit: 26_214_400 })
      : path === FLAGS
        ? Response.json({})
        : path === "/grantr/v1/checks"
          ? Response.json([false])
          : undefined;

test("on a phone, a file whose app has no editor here says it can't be edited in this window", async () => {
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const { screen } = await open(PAGE, serving, undefined, { editors: {} });
  const said = screen.getByText(/^WordCraft can't be edited in this window\. /);
  await expect.element(said).toBeVisible();
  await expect
    .element(screen.getByRole("button", { name: "Check out and download" }))
    .toBeVisible();
});
