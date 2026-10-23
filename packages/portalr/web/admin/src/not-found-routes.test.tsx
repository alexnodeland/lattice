/**
 * What admin shows at an address with nothing there (portalr ADR-0068): a page under a tenant the
 * reader administers is not found in the frame's own main, and a tenant they don't administer is
 * said so on a plain page.
 */

import { expect, test } from "vitest";
import { open } from "./test/admin";

const nothing = async () => undefined;

test("a page under a tenant one administers is not found inside the frame, with one main", async () => {
  const { screen } = await open("/t/acme/zzz", [], nothing);
  const heading = screen.getByRole("heading", { level: 1, name: "Page not found" });
  await expect.element(heading).toHaveFocus();
  expect(document.querySelectorAll("main")).toHaveLength(1);
  // In the frame: its header, and the page in its one main.
  expect(document.querySelector("[data-frame-header]")).not.toBeNull();
  expect(document.querySelector("main")?.contains(heading.element())).toBe(true);
  await expect
    .element(screen.getByRole("link", { name: "Home" }).last())
    .toHaveAttribute("href", "/t/acme");
  await expect.poll(() => document.title).toMatch(/^Page not found · /);
});

test("a tenant one doesn't administer is said so", async () => {
  const { screen } = await open("/t/globex", [], nothing);
  await expect
    .element(screen.getByRole("heading", { level: 1, name: "Not a tenant you administer" }))
    .toBeVisible();
  await expect.poll(() => document.title).toMatch(/^Not a tenant you administer · /);
  expect(document.querySelectorAll("main")).toHaveLength(1);
});
