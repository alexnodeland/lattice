import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { StatCard } from "./stat-card";
import { StatusBadge } from "./status-badge";

test("a stat card is an article named by its title, with its figure and what it is", async () => {
  const screen = await render(
    <StatCard title="Members" figure="4" action={<a href="#access">Access</a>}>
      3 people and 1 service principal
    </StatCard>,
  );
  const card = screen.getByRole("article", { name: "Members" });
  await expect.element(card).toHaveAttribute("aria-busy", "false");
  await expect.element(card.getByText("4", { exact: true })).toBeVisible();
  await expect.element(card.getByText("3 people and 1 service principal")).toBeVisible();
  await expect.element(card.getByRole("link", { name: "Access" })).toBeVisible();
});

test("a card that can't read says why, with its state as a badge", async () => {
  const screen = await render(
    <StatCard
      title="Spend"
      figure={null}
      badge={<StatusBadge tone="stopped">Not configured</StatusBadge>}
    >
      LiteLLM isn't configured.
    </StatCard>,
  );
  const card = screen.getByRole("article", { name: "Spend" });
  await expect.element(card.getByText("Not configured")).toBeVisible();
  await expect.element(card.getByText("LiteLLM isn't configured.")).toBeVisible();
});

test("a card being read is busy", async () => {
  const screen = await render(
    <StatCard title="Feedback" figure={null} busy>
      Reading…
    </StatCard>,
  );
  await expect
    .element(screen.getByRole("article", { name: "Feedback" }))
    .toHaveAttribute("aria-busy", "true");
});
