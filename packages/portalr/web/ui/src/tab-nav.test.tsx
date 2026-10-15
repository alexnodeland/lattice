import { expect, test } from "vitest";
import { page } from "vitest/browser";
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

test("on a phone, the tabs stay on one row, which scrolls", async () => {
  await page.viewport(390, 844);
  const screen = await render(
    <TabNav label="Access">
      {["Members", "Groups", "Keys", "Roles", "Grants"].map((part) => (
        <TabLink key={part} href={`#${part}`}>
          {part}
        </TabLink>
      ))}
    </TabNav>,
  );
  const tabs = screen.getByRole("navigation", { name: "Access" });
  await expect.element(tabs).toBeVisible();
  const tops = tabs
    .getByRole("link")
    .elements()
    .map((link) => link.getBoundingClientRect().top);
  expect(new Set(tops).size).toBe(1);
  const row = tabs.element();
  expect(getComputedStyle(row).overflowX).toBe("auto");
});
