import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { TabLink, TabNav } from "./tab-nav";

test("a tab bar names its links, and marks the current part", async () => {
  const screen = await render(
    <TabNav label="Access">
      <TabLink href="#members" aria-current="page">
        Members
      </TabLink>
      <TabLink href="#keys">Keys</TabLink>
    </TabNav>,
  );
  const tabs = screen.getByRole("navigation", { name: "Access" });
  await expect
    .element(tabs.getByRole("link", { name: "Members" }))
    .toHaveAttribute("aria-current", "page");
  await expect.element(tabs.getByRole("link", { name: "Keys" })).toHaveAttribute("href", "#keys");
});

test("tabs too many for their room stay on one row, which scrolls", async () => {
  const screen = await render(
    <div style={{ width: 240 }}>
      <TabNav label="Access">
        {["Members", "Groups", "Keys", "Roles", "Grants"].map((part) => (
          <TabLink key={part} href={`#${part}`}>
            {part}
          </TabLink>
        ))}
      </TabNav>
    </div>,
  );
  const tabs = screen.getByRole("navigation", { name: "Access" });
  await expect.element(tabs).toBeVisible();
  const row = tabs.element();
  // They don't fit, and don't wrap: one row, scrolled sideways.
  expect(row.scrollWidth).toBeGreaterThan(row.clientWidth);
  const tops = tabs
    .getByRole("link")
    .elements()
    .map((link) => Math.round(link.getBoundingClientRect().top));
  expect(new Set(tops).size).toBe(1);
  row.scrollLeft = row.scrollWidth;
  expect(row.scrollLeft).toBeGreaterThan(0);
});
