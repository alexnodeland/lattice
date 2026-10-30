import { expect, onTestFinished, test } from "vitest";
import { commands, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { glyphs } from "./icons";
import { NavLink, SideNav } from "./side-nav";
import { contrast, token } from "./test/colours";

function Nav() {
  return (
    <SideNav label="Workspace">
      <NavLink href="#threads" icon={glyphs.messageSquare} count={1} aria-current="page">
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

test("the current area sits on the wash in the working colour, where the rest are plain", async () => {
  const screen = await render(<Nav />);
  const current = screen.getByRole("link", { name: /^Threads/ });
  await expect.element(current).toHaveAttribute("aria-current", "page");
  const style = getComputedStyle(current.element());
  expect(style.color).toBe(token("accent"));
  expect(style.backgroundColor).toBe(token("wash"));
  const other = getComputedStyle(screen.getByRole("link", { name: "Artifacts" }).element());
  expect(other.color).toBe(token("fg"));
  expect(other.backgroundColor).toBe("rgba(0, 0, 0, 0)");
  expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
  // And in the heavier weight, a cue beside the colour (portalr ADR-0081); a page inside it too.
  expect(style.fontWeight).toBe("600");
  expect(other.fontWeight).toBe("500");
});

test("the area a page inside belongs to is marked as the page's own is: wash, colour and weight", async () => {
  const screen = await render(
    <SideNav label="Workspace">
      <NavLink href="#threads" aria-current="true">
        Threads
      </NavLink>
    </SideNav>,
  );
  const style = getComputedStyle(screen.getByRole("link", { name: "Threads" }).element());
  expect(style.fontWeight).toBe("600");
  expect(style.color).toBe(token("accent"));
  expect(style.backgroundColor).toBe(token("wash"));
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

test("under forced colours, the area shown keeps an outline, and the others none", async () => {
  onTestFinished(() => commands.forcedColors(false));
  const screen = await render(<Nav />);
  await commands.forcedColors(true);
  await expect.poll(() => matchMedia("(forced-colors: active)").matches).toBe(true);
  const style = (name: string) =>
    getComputedStyle(screen.getByRole("link", { name: new RegExp(`^${name}`) }).element());
  expect(style("Threads").outlineStyle).toBe("solid");
  expect(Number.parseFloat(style("Threads").outlineWidth)).toBeGreaterThan(0);
  const others = screen
    .getByRole("link")
    .elements()
    .filter((link) => !link.hasAttribute("aria-current"));
  expect(others.length).toBeGreaterThan(0);
  for (const other of others) {
    expect(getComputedStyle(other).outlineStyle).toBe("none");
  }
});

test("under forced colours, the current area focused from the keyboard has its ring outside", async () => {
  onTestFinished(() => commands.forcedColors(false));
  const screen = await render(<Nav />);
  await commands.forcedColors(true);
  await expect.poll(() => matchMedia("(forced-colors: active)").matches).toBe(true);
  const current = screen.getByRole("link", { name: /^Threads/ }).element();
  expect(Number.parseFloat(getComputedStyle(current).outlineOffset)).toBeLessThan(0);
  await userEvent.tab();
  expect(document.activeElement).toBe(current);
  expect(Number.parseFloat(getComputedStyle(current).outlineOffset)).toBeGreaterThan(0);
});
