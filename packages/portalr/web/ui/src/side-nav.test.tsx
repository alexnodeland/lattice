import { MessageSquare } from "lucide-react";
import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { NavLink, SideNav } from "./side-nav";
import { contrast, token } from "./test/colours";

function Nav() {
  return (
    <SideNav label="Workspace">
      <NavLink href="#threads" icon={MessageSquare} count={1} aria-current="page">
        Threads
      </NavLink>
      <NavLink href="#artifacts">Artifacts</NavLink>
      <NavLink href="#runs" count={0}>
        Runs
      </NavLink>
    </SideNav>
  );
}

test("the navigation is named, and each area is a link named by its word and what waits there", async () => {
  const screen = await render(<Nav />);
  const nav = screen.getByRole("navigation", { name: "Workspace" });
  await expect.element(nav.getByRole("link", { name: "Threads, 1 waiting for you" })).toBeVisible();
  await expect.element(nav.getByRole("link", { name: "Artifacts" })).toBeVisible();
  await expect.element(nav.getByRole("link", { name: "Runs", exact: true })).toBeVisible();
});

test("the current area is marked, on the wash, in the working colour", async () => {
  const screen = await render(<Nav />);
  const current = screen.getByRole("link", { name: /^Threads/ });
  await expect.element(current).toHaveAttribute("aria-current", "page");
  const style = getComputedStyle(current.element());
  expect(style.backgroundColor).toBe(token("wash"));
  expect(style.color).toBe(token("accent"));
  expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
  expect(current.element().querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
});

test("a link renders as the element it is given, such as the router's", async () => {
  const screen = await render(
    <SideNav label="Workspace">
      <NavLink render={<a href="#proposals" data-router="" />}>Proposals</NavLink>
    </SideNav>,
  );
  await expect
    .element(screen.getByRole("link", { name: "Proposals" }))
    .toHaveAttribute("data-router", "");
});
