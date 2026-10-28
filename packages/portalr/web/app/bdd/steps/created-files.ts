/**
 * Files the agent creates blank (lattice#874): each one's card in the thread, which says it was
 * created empty until a change to it is accepted, and then reads as a file (portalr ADR-0055).
 */

import { expect, type Page } from "@playwright/test";
import { Then, When } from "./fixtures";

/** A file's card, named for the file: in the thread, or beside it, where the newest goes. */
const card = (page: Page, name: string) =>
  page.getByRole("main").getByRole("listitem", { name, exact: true });

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

/** A proposal in the thread, by its summary alone: one summary may begin another. */
const proposal = (page: Page, what: string) =>
  page.getByRole("region", { name: `Proposal: ${what}`, exact: true });

Then("the proposal {string} waits for review", async ({ page }, what: string) => {
  await expect(proposal(page, what).getByRole("button", { name: "Accept" })).toBeVisible();
});

When("they accept the proposal {string}", async ({ page }, what: string) => {
  await proposal(page, what).getByRole("button", { name: "Accept" }).click();
});

Then("{string} is a file to read", async ({ page }, name: string) => {
  const file = card(page, name);
  await expect(file).not.toContainText("Created empty.");
  await expect(file.getByRole("radio").first()).toBeVisible();
});
