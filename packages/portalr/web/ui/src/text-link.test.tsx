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

test("a subtle link is in the text's colour, its underline quiet until hovered", async () => {
  const screen = await render(
    <TextLink variant="subtle" href="#trace">
      trace_1
    </TextLink>,
  );
  const link = screen.getByRole("link", { name: "trace_1" }).element();
  expect(getComputedStyle(link).color).toBe(token("fg"));
  expect(getComputedStyle(link).textDecorationColor).toBe(token("edge"));
  // Its underline is a mark, 3:1 or more on the paper; it stands alone, never in running text.
  expect(contrast(token("edge"), token("paper"))).toBeGreaterThanOrEqual(3);
  await userEvent.hover(link);
  expect(getComputedStyle(link).color).toBe(token("accent"));
});

test("a nav link is underlined only when hovered", async () => {
  const screen = await render(
    <TextLink variant="nav" href="#runs">
      Runs
    </TextLink>,
  );
  const link = screen.getByRole("link", { name: "Runs" }).element();
  expect(getComputedStyle(link).textDecorationLine).toBe("none");
  await userEvent.hover(link);
  expect(getComputedStyle(link).textDecorationLine).toBe("underline");
});

test("an external link opens a new tab, safely, and says so", async () => {
  const screen = await render(
    <TextLink variant="external" href="https://example.com">
      Langfuse
    </TextLink>,
  );
  const link = screen.getByRole("link", { name: "Langfuse (opens in a new tab)" }).element();
  expect(link.getAttribute("target")).toBe("_blank");
  expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  expect(link.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  expect(getComputedStyle(link).display).toBe("inline");
});

test("a caller can't weaken an external link's new tab", async () => {
  const screen = await render(
    <TextLink variant="external" href="https://example.com" target="_self" rel="opener">
      Grafana
    </TextLink>,
  );
  const link = screen.getByRole("link", { name: "Grafana (opens in a new tab)" }).element();
  expect(link.getAttribute("target")).toBe("_blank");
  expect(link.getAttribute("rel")).toBe("noopener noreferrer");
});

test("a long external link wraps, and its mark stays with its last word", async () => {
  const screen = await render(
    <p style={{ width: "10rem" }}>
      <TextLink variant="external" href="https://example.com">
        The tenant's traces in Grafana, from Tempo
      </TextLink>
    </p>,
  );
  const link = screen.getByRole("link").element();
  expect(link.getClientRects().length).toBeGreaterThan(1);
  const mark = link.querySelector("svg") as Element;
  const lines = [...link.getClientRects()];
  expect(Math.round(mark.getBoundingClientRect().bottom)).toBeLessThanOrEqual(
    Math.round((lines.at(-1) as DOMRect).bottom),
  );
});
