/**
 * admin on a phone (portalr ADR-0082): Invite… opens its form as a dialog along the bottom, a
 * sheet, with the form's first field focused, closed by Escape with the focus back on its button.
 */

import { afterEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { TENANT_ACTIONS } from "./access";
import { open } from "./test/admin";

async function serve(_request: Request, path: string): Promise<Response | undefined> {
  if (path === "/grantr/v1/catalog")
    return Response.json({
      roles: [{ name: "owner", kinds: ["tenant"] }],
      custom_actions: [],
      custom_kinds: [],
    });
  if (path === "/grantr/v1/tenants/acme/members")
    return Response.json([{ kind: "user", id: "bob" }]);
  if (path.startsWith("/grantr/v1/tenants/acme/")) return Response.json([]);
  return undefined;
}
afterEach(() => vi.unstubAllGlobals());

test("Invite… opens its form as a sheet, the field focused, and Escape brings the focus back", async () => {
  await page.viewport(390, 844);
  const { screen } = await open("/t/acme/access/members", TENANT_ACTIONS, serve);
  await expect.element(screen.getByText("bob").first()).toBeInTheDocument();
  await screen.getByRole("button", { name: "Invite…" }).click();
  const dialog = screen.getByRole("dialog", { name: "Invite someone" });
  await expect.element(dialog).toBeVisible();
  await expect
    .poll(() => Math.round(dialog.element().getBoundingClientRect().bottom))
    .toBe(window.innerHeight);
  expect(Math.round(dialog.element().getBoundingClientRect().width)).toBe(window.innerWidth);
  await expect.element(dialog.getByRole("textbox").first()).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  await expect
    .element(screen.getByRole("dialog", { name: "Invite someone" }))
    .not.toBeInTheDocument();
  await expect.element(screen.getByRole("button", { name: "Invite…" })).toHaveFocus();
});
