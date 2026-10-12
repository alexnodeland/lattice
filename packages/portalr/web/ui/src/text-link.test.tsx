import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { contrast, token } from "./test/colours";
import { TextLink } from "./text-link";

test("a link is in the working colour, underlined, readable on the paper", async () => {
  const screen = await render(<TextLink href="#plans">plans</TextLink>);
  const link = screen.getByRole("link", { name: "plans" }).element();
  const style = getComputedStyle(link);
  expect(style.color).toBe(token("accent"));
  expect(style.textDecorationLine).toBe("underline");
  expect(contrast(style.color, token("paper"))).toBeGreaterThanOrEqual(4.5);
});

test("a router's link renders through it, with the link's look", async () => {
  const screen = await render(
    <TextLink render={<a data-router="yes" href="#notes" />}>notes</TextLink>,
  );
  const link = screen.getByRole("link", { name: "notes" }).element();
  expect(link.getAttribute("data-router")).toBe("yes");
  expect(link.classList).toContain("underline");
});

test("a link reached by the keyboard shows the focus ring", async () => {
  const screen = await render(<TextLink href="#acme">acme</TextLink>);
  await userEvent.tab();
  const link = screen.getByRole("link", { name: "acme" }).element();
  expect(link.matches(":focus-visible")).toBe(true);
  expect(getComputedStyle(link).outlineColor).toBe(token("focus"));
});

test("a caller's classes override the link's own", async () => {
  const screen = await render(
    <TextLink href="#x" className="no-underline">
      x
    </TextLink>,
  );
  const link = screen.getByRole("link", { name: "x" }).element();
  expect(link.classList).toContain("no-underline");
  expect(link.classList).not.toContain("underline");
});
