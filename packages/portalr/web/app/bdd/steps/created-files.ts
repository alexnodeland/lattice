/**
 * Files the agent creates blank (lattice#874): each one's card in the thread, which says it was
 * created empty until a change to it is accepted, and then reads as a file (portalr ADR-0055).
 */

import { expect, type Page } from "@playwright/test";
import { card } from "./diagrams";
import { Then, When } from "./fixtures";

Then(
  "{string} was created empty, its changes waiting for review",
  async ({ page }, name: string) => {
    const created = card(page, name);
    await expect(created).toContainText("Created empty.");
    await expect(
      created.getByRole("link", { name: "The agent's changes are waiting for your review." }),
    ).toBeVisible();
  },
);

/**
 * A proposal in the thread, by its whole summary: "Write the travel plan" begins "Write the travel
 * plan's slides", so threads.ts's steps, which match a summary's start, would find both.
 */
const proposal = (page: Page, what: string) =>
  page.getByRole("region", { name: `Proposal: ${what}`, exact: true });

Then("the proposal {string} waits for review", async ({ page }, what: string) => {
  await expect(proposal(page, what).getByRole("button", { name: "Accept" })).toBeVisible();
});

/** What a native file's proposal does, in words, which opens to each of its changes (ADR-0089). */
Then(
  "the proposal {string} says {string}, change by change",
  async ({ page }, what: string, said: string) => {
    const line = proposal(page, what).getByRole("button", { name: said });
    await line.click();
    await expect(line).toHaveAttribute("aria-expanded", "true");
    const changes = proposal(page, what).getByRole("list", { name: "Its changes" });
    await expect(changes.getByRole("listitem")).toHaveCount(3);
  },
);

When("they accept the proposal {string}", async ({ page }, what: string) => {
  await proposal(page, what).getByRole("button", { name: "Accept" }).click();
  await expect(proposal(page, what)).toContainText("Accepted");
});

Then("{string} is a file to read", async ({ page }, name: string) => {
  const file = card(page, name);
  await expect(file).not.toContainText("Created empty.");
  // The normal card's facts, which the created card, with no size, pages or version, never shows.
  await expect(file.getByText(/· version 2$/)).toBeVisible();
});
