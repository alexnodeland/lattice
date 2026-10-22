import { expect, test } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { AppShell } from "./app-shell";
import type { Ui } from "./marks";
import { NavLink, SideNav } from "./side-nav";
import { viewport } from "./test/viewport";

async function shell(width: number, ui: Ui = "app", withNav = true) {
  await viewport(width);
  return render(
    <AppShell
      ui={ui}
      home={<a href="#home" />}
      switcher={<button type="button">Workspace: acme / notes</button>}
      account={<button type="button">Account: Alex</button>}
      nav={
        withNav && (
          <SideNav label="Workspace">
            <NavLink href="#threads">Threads</NavLink>
            <NavLink href="#runs">Runs</NavLink>
          </SideNav>
        )
      }
    >
      <h1>Threads</h1>
    </AppShell>,
  );
}

test("from 1024 pixels, a rail holds the mark, the switcher, the navigation and the account", async () => {
  const screen = await shell(1280);
  await expect.element(screen.getByRole("link", { name: "portalr" })).toBeVisible();
  await expect.element(screen.getByRole("navigation", { name: "Workspace" })).toBeVisible();
  await expect
    .element(screen.getByRole("button", { name: "Workspace: acme / notes" }))
    .toBeVisible();
  await expect.element(screen.getByRole("button", { name: "Account: Alex" })).toBeVisible();
  await expect.element(screen.getByRole("button", { name: "Menu" })).not.toBeInTheDocument();
  await expect.element(screen.getByRole("main")).toHaveTextContent("Threads");
});

test("the first stop is a link past the frame, to the content", async () => {
  const screen = await shell(1280);
  await userEvent.tab();
  const skip = screen.getByRole("link", { name: "Skip to content" });
  await expect.element(skip).toHaveFocus();
  await expect.element(skip).toHaveAttribute("href", "#main");
});

test("narrower, the navigation waits behind Menu, in a drawer that keeps the focus", async () => {
  const screen = await shell(390);
  await expect.element(screen.getByRole("navigation")).not.toBeInTheDocument();
  const menu = screen.getByRole("button", { name: "Menu" });
  await menu.click();
  const drawer = screen.getByRole("dialog", { name: "Navigation" });
  await expect.element(drawer).toHaveAttribute("aria-modal", "true");
  await expect.element(drawer.getByRole("navigation", { name: "Workspace" })).toBeVisible();
  // The switcher and the account are in the drawer too, not only on the bar behind it.
  await expect
    .element(drawer.getByRole("button", { name: "Workspace: acme / notes" }))
    .toBeVisible();
  await expect.element(drawer.getByRole("button", { name: "Account: Alex" })).toBeVisible();
  await expect.element(screen.getByRole("main")).not.toBeInTheDocument();
  for (let i = 0; i < 5; i += 1) {
    await userEvent.tab();
    // The drawer's focus guard returns the focus a moment after it leaves: wait for it.
    await expect.poll(() => drawer.element().contains(document.activeElement)).toBe(true);
  }
  await userEvent.keyboard("{Escape}");
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
  await expect.element(menu).toHaveFocus();
});

test("following a link in the drawer, or Close, closes it", async () => {
  const screen = await shell(390);
  await screen.getByRole("button", { name: "Menu" }).click();
  await screen.getByRole("link", { name: "Runs" }).click();
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
  await screen.getByRole("button", { name: "Menu" }).click();
  await screen.getByRole("button", { name: "Close" }).click();
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
});

test("widening past the rail's width closes the drawer", async () => {
  const screen = await shell(390);
  await screen.getByRole("button", { name: "Menu" }).click();
  await expect.element(screen.getByRole("dialog")).toBeVisible();
  await page.viewport(1280, 800);
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
  await expect.element(screen.getByRole("navigation", { name: "Workspace" })).toBeVisible();
});

test("with the drawer closed, the switcher, the navigation and the account are each there once", async () => {
  const screen = await shell(1280);
  expect(screen.container.querySelectorAll("nav")).toHaveLength(1);
  expect(screen.getByRole("button", { name: "Workspace: acme / notes" }).elements()).toHaveLength(
    1,
  );
  expect(screen.getByRole("button", { name: "Account: Alex" }).elements()).toHaveLength(1);
});

test("with the drawer open, the switcher and the account are there twice: behind it, and in it", async () => {
  const screen = await shell(390);
  await screen.getByRole("button", { name: "Menu" }).click();
  // The page behind a modal drawer is hidden from the accessibility tree, so count in the DOM.
  const accounts = [...document.querySelectorAll("button")].filter(
    (button) => button.textContent === "Account: Alex",
  );
  expect(accounts).toHaveLength(2);
});

test("a page with no navigation has a rail of the mark, the switcher and the account alone", async () => {
  const screen = await shell(1280, "app", false);
  await expect.element(screen.getByRole("navigation")).not.toBeInTheDocument();
  await expect
    .element(screen.getByRole("button", { name: "Workspace: acme / notes" }))
    .toBeVisible();
  await expect.element(screen.getByRole("button", { name: "Account: Alex" })).toBeVisible();
});

test("a page with no navigation still has its drawer: Menu opens it, with no navigation in it", async () => {
  const screen = await shell(390, "app", false);
  const menu = screen.getByRole("button", { name: "Menu" });
  await expect.element(menu).toBeVisible();
  await menu.click();
  const drawer = screen.getByRole("dialog", { name: "Navigation" });
  await expect.element(drawer).toBeVisible();
  await expect.element(drawer.getByRole("navigation")).not.toBeInTheDocument();
  await expect.element(drawer.getByRole("button", { name: "Account: Alex" })).toBeVisible();
});

test("admin's frame is named for admin, and shows its own mark", async () => {
  const app = await shell(1280);
  const appMark = app.getByRole("link", { name: "portalr" }).element().innerHTML;
  app.unmount();
  const admin = await shell(1280, "admin");
  const adminLink = admin.getByRole("link", { name: "portalr admin" });
  await expect.element(adminLink).toBeVisible();
  expect(adminLink.element().innerHTML).not.toBe(appMark);
});

async function tall(width: number) {
  await viewport(width);
  return render(
    <AppShell home={<a href="#home" />} switcher={<span>acme</span>} account={<span>alice</span>}>
      <div style={{ height: "300vh" }} />
      <p id="far">Far down</p>
      <div style={{ height: "300vh" }} />
    </AppShell>,
  );
}

test("from 1024 pixels, the rail stays in the window while the page scrolls past it", async () => {
  await tall(1280);
  window.scrollTo(0, document.documentElement.scrollHeight);
  const rail = (document.querySelector("header") as HTMLElement).getBoundingClientRect();
  expect(window.scrollY).toBeGreaterThan(0);
  expect(rail.top).toBe(0);
  expect(rail.bottom).toBeCloseTo(window.innerHeight, 0);
  window.scrollTo(0, 0);
});

test("narrower, what is scrolled to stops below the pinned header, not under it", async () => {
  await tall(390);
  const header = document.querySelector("header") as HTMLElement;
  const room = Number.parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop);
  expect(room).toBeGreaterThanOrEqual(header.getBoundingClientRect().height);
  document.getElementById("far")?.scrollIntoView();
  expect(document.getElementById("far")?.getBoundingClientRect().top).toBeGreaterThanOrEqual(
    header.getBoundingClientRect().bottom,
  );
  window.scrollTo(0, 0);
});

test("at the rail's width, nothing is pinned above the page, so nothing is held clear of it", async () => {
  await tall(1280);
  expect(getComputedStyle(document.documentElement).scrollPaddingTop).toBe("0px");
});
