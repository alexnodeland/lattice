import { Maximize2 } from "lucide-react";
import { expect, test } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { IconButton } from "./icon-button";
import { token } from "./test/colours";

test("an icon button is named by its label, a target 24px or more, its icon hidden", async () => {
  const screen = await render(<IconButton label="Full view" icon={Maximize2} />);
  const button = screen.getByRole("button", { name: "Full view" }).element();
  const box = button.getBoundingClientRect();
  expect(box.width).toBeGreaterThanOrEqual(24);
  expect(box.height).toBeGreaterThanOrEqual(24);
  expect(button.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
});

test("its label shows as a tooltip when the keyboard reaches it", async () => {
  await render(<IconButton label="Full view" icon={Maximize2} />);
  await userEvent.tab();
  const tip = page.getByText("Full view", { exact: true });
  await expect.element(tip).toBeVisible();
  expect(getComputedStyle(tip.element()).color).toBe(token("fg"));
});

test("a pressed icon button says so, in the wash", async () => {
  const screen = await render(<IconButton label="Helpful" icon={Maximize2} aria-pressed />);
  const button = screen.getByRole("button", { name: "Helpful", pressed: true }).element();
  expect(getComputedStyle(button).color).toBe(token("accent"));
});

test("an icon button can be a link, such as the router's", async () => {
  const screen = await render(
    <IconButton label="Open its page" icon={Maximize2} render={<a href="#page">page</a>} />,
  );
  const link = screen.getByRole("link", { name: "Open its page" }).element();
  expect(link.getAttribute("href")).toBe("#page");
});
