import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { StatCard } from "./stat-card";

test("a stat card is a region named by its title, with its figure and what it is", async () => {
  const screen = await render(
    <StatCard title="Members" figure={4} action={<a href="#access">Access</a>}>
      3 people and 1 service principal
    </StatCard>,
  );
  const card = screen.getByRole("region", { name: "Members" });
  await expect.element(card).toHaveTextContent("Members43 people and 1 service principalAccess");
  await expect.element(card.getByRole("link", { name: "Access" })).toBeVisible();
});

test("a card with no figure says why", async () => {
  const screen = await render(
    <StatCard title="Spend" figure={null}>
      LiteLLM isn't configured.
    </StatCard>,
  );
  await expect
    .element(screen.getByRole("region", { name: "Spend" }))
    .toHaveTextContent("SpendLiteLLM isn't configured.");
});
