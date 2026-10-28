import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { AppShell } from "./app-shell";
import { viewport } from "./test/viewport";

async function shell(width: number) {
  await viewport(width);
  return render(
    <AppShell
      home={<a href="#home" />}
      switcher={<button type="button">Workspace: acme / notes</button>}
      nav={
        <nav aria-label="Workspace">
          <a href="#threads">Threads</a>
        </nav>
      }
      search={<button type="button">Search</button>}
      waiting={<a href="#needs">2 need you</a>}
      account={<button type="button">Account: Alex</button>}
    >
      <h1>Threads</h1>
    </AppShell>,
  );
}

test("from 1024 pixels, one bar holds the mark, the switcher, the areas, and in its corner the search, what waits and the account", async () => {
  const screen = await shell(1280);
  const bar = screen.getByRole("banner");
  await expect.element(bar.getByRole("link", { name: "portalr" })).toBeVisible();
  await expect.element(bar.getByRole("navigation", { name: "Workspace" })).toBeVisible();
  await expect.element(bar.getByRole("button", { name: "Search" })).toBeVisible();
  await expect.element(bar.getByRole("link", { name: "2 need you" })).toBeVisible();
  await expect.element(bar.getByRole("button", { name: "Account: Alex" })).toBeVisible();
  // The areas are on the bar alone, and there is no drawer to open.
  expect(screen.getByRole("navigation", { name: "Workspace" }).elements()).toHaveLength(1);
  await expect.element(screen.getByRole("button", { name: "Menu" })).not.toBeInTheDocument();
});

test("narrower, the bar has no mark, and the areas are the page's first row", async () => {
  const screen = await shell(390);
  expect(screen.getByRole("link", { name: "portalr" }).query()).toBeNull();
  const areas = screen.getByRole("main").getByRole("navigation", { name: "Workspace" });
  await expect.element(areas).toBeVisible();
  await expect.element(screen.getByRole("button", { name: "Search" })).toBeVisible();
});

test("the first stop is a link past the bar, to the content", async () => {
  const screen = await shell(1280);
  await userEvent.tab();
  await expect.element(screen.getByRole("link", { name: "Skip to content" })).toHaveFocus();
});

test("the bar stays at the top as the page scrolls, and what is scrolled to stops below it", async () => {
  await viewport(1280);
  await render(
    <AppShell home={<a href="#home" />} switcher={<span>acme</span>} account={<span>a</span>}>
      <div style={{ height: "300vh" }} />
    </AppShell>,
  );
  window.scrollTo(0, 1000);
  const bar = document.querySelector("header") as HTMLElement;
  expect(bar.getBoundingClientRect().top).toBe(0);
  const room = Number.parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop);
  expect(room).toBeGreaterThanOrEqual(bar.getBoundingClientRect().height);
  window.scrollTo(0, 0);
});
