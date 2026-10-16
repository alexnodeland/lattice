import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { AppShell } from "./app-shell";
import { PageHeader } from "./page-header";
import { SectionTitle } from "./section-title";
import { StatCard } from "./stat-card";

const size = (element: Element) => Number.parseFloat(getComputedStyle(element).fontSize);
const weight = (element: Element) => Number(getComputedStyle(element).fontWeight);

test("a page's title is larger than a section's, which is larger than prose, and none is heavier than 600", async () => {
  const screen = await render(
    <>
      <PageHeader title="Usage" meta="What the tenant's agents spent" />
      <SectionTitle>By workspace</SectionTitle>
      <p>Prose</p>
    </>,
  );
  const page = screen.getByRole("heading", { level: 1 }).element();
  const section = screen.getByRole("heading", { level: 2 }).element();
  const prose = screen.getByText("Prose").element();
  expect(size(page)).toBeGreaterThan(size(section));
  expect(size(section)).toBeGreaterThan(size(prose));
  expect(weight(page)).toBeLessThanOrEqual(600);
  expect(weight(section)).toBeLessThanOrEqual(600);
});

test("a page's line about it is the body's size, in the quiet text", async () => {
  const screen = await render(<PageHeader title="Usage" meta="What the tenant's agents spent" />);
  const meta = screen.getByText("What the tenant's agents spent").element();
  expect(size(meta)).toBe(14);
});

test("cards in a row are as tall as the tallest, and each action sits at its card's foot", async () => {
  const screen = await render(
    <div className="grid grid-cols-2 gap-4" style={{ width: 600 }}>
      <StatCard title="Members" figure="5" action={<a href="#members">Members</a>}>
        4 people and 1 service principal, in a line long enough to wrap on a narrow card
      </StatCard>
      <StatCard title="Spend" figure="$85.00" action={<a href="#usage">Usage</a>}>
        of $100
      </StatCard>
    </div>,
  );
  const [first, second] = screen.getByRole("article").elements();
  expect(first?.getBoundingClientRect().height).toBeCloseTo(
    second?.getBoundingClientRect().height ?? 0,
    0,
  );
  const links = ["Members", "Usage"].map(
    (name) => screen.getByRole("link", { name }).element().getBoundingClientRect().bottom,
  );
  expect(links[0]).toBeCloseTo(links[1] ?? 0, 0);
});

test("a card's figure keeps its decimal point tight, and lines its digits up", async () => {
  const screen = await render(<StatCard title="Spend" figure="$1,250.50" />);
  const digits = [...screen.getByRole("article").element().querySelectorAll(".tabular-nums")].map(
    (span) => span.textContent,
  );
  expect(digits).toEqual(["1", "250", "50"]);
});

test("a page's content is no wider than the page width, and is centred on a wide screen", async () => {
  const screen = await render(
    <div style={{ width: 1800 }}>
      <AppShell home={<a href="#home" />} switcher={<span>s</span>} account={<span>a</span>}>
        <p>Content</p>
      </AppShell>
    </div>,
  );
  const content = screen.getByText("Content").element().parentElement as HTMLElement;
  const width = Number.parseFloat(getComputedStyle(document.documentElement).fontSize) * 75;
  expect(content.getBoundingClientRect().width).toBeLessThanOrEqual(width + 1);
  const main = content.parentElement as HTMLElement;
  const left = content.getBoundingClientRect().left - main.getBoundingClientRect().left;
  const right = main.getBoundingClientRect().right - content.getBoundingClientRect().right;
  expect(Math.abs(left - right)).toBeLessThan(2);
});
