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
