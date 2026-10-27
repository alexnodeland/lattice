/**
 * A toolbar's forms on a phone (portalr ADR-0082): a form that makes something opens as a sheet,
 * a filter stays a card beneath the row so what it finds is seen as it is typed, and what was
 * typed survives the phone turning through the width where one becomes the other. On a tablet
 * with a finger, admin's compact rows are still a finger's height.
 */

import { TextField } from "@portalr/ui";
import { afterEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { TENANT_ACTIONS } from "./access";
import { Folded, Toolbar } from "./folded";
import { open } from "./test/admin";

afterEach(() => vi.unstubAllGlobals());

test("a filter stays a card on a phone; a form opens as a sheet and keeps its words when the phone turns", async () => {
  await page.viewport(390, 844);
  const screen = await render(
    <Toolbar>
      <Folded title="Find" action="Find…" kind="filter">
        <TextField label="Words" />
      </Folded>
      <Folded title="Invite someone" action="Invite…">
        <TextField label="Email" />
      </Folded>
    </Toolbar>,
  );
  await screen.getByRole("button", { name: "Find…" }).click();
  await expect.element(screen.getByRole("textbox", { name: "Words" })).toHaveFocus();
  expect(screen.getByRole("dialog").elements()).toHaveLength(0);
  await screen.getByRole("button", { name: "Invite…" }).click();
  const sheet = screen.getByRole("dialog", { name: "Invite someone" });
  await expect.element(sheet).toBeVisible();
  await expect.element(screen.getByRole("textbox", { name: "Email" })).toHaveFocus();
  await userEvent.keyboard("bob@acme");
  // Turned to a tablet's width: a card, the words kept; turned back: the sheet, kept still.
  await page.viewport(1024, 768);
  await expect
    .element(screen.getByRole("dialog", { name: "Invite someone" }))
    .not.toBeInTheDocument();
  await expect.element(screen.getByRole("textbox", { name: "Email" })).toHaveValue("bob@acme");
  await page.viewport(390, 844);
  await expect.element(screen.getByRole("dialog", { name: "Invite someone" })).toBeVisible();
  await expect.element(screen.getByRole("textbox", { name: "Email" })).toHaveValue("bob@acme");
});

async function serve(_request: Request, path: string): Promise<Response | undefined> {
  if (path === "/grantr/v1/catalog") {
    return Response.json({
      roles: [{ name: "owner", kinds: ["tenant"] }],
      custom_actions: [],
      custom_kinds: [],
    });
  }
  if (path === "/grantr/v1/tenants/acme/members") {
    return Response.json([
      { kind: "user", id: "bob" },
      { kind: "user", id: "alice" },
    ]);
  }
  if (path.startsWith("/grantr/v1/tenants/acme/")) {
    return Response.json([]);
  }
  return undefined;
}

test("on a tablet with a finger, a member's compact row is a finger's height", async () => {
  await page.viewport(1024, 768);
  const { screen } = await open("/t/acme/access/members", TENANT_ACTIONS, serve);
  const row = screen.getByRole("row", { name: /bob/ });
  await expect.element(row).toBeVisible();
  expect(row.element().getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
});
