import { expect, type Page } from "@playwright/test";
import { createBdd } from "playwright-bdd";

const { Then, When } = createBdd();

const messages = (page: Page) => page.getByRole("log", { name: "Messages" });
const assistant = (page: Page) =>
  messages(page).getByRole("listitem").filter({ hasText: "Assistant" }).last();

When("they start the thread {string}", async ({ page }, title: string) => {
  await page.getByLabel("New thread").fill(title);
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByRole("heading", { level: 2 })).toHaveText(title);
});

When("they post {string}", async ({ page }, message: string) => {
  await page.getByRole("textbox", { name: "Message" }).fill(message);
  await page.getByRole("button", { name: "Send" }).click();
  // The person's message is a paragraph of its own; the agent's echo says more around it.
  const posted = messages(page).getByRole("paragraph").filter({ hasText: message }).first();
  await expect(posted).toHaveText(message);
});

Then("the assistant says {string}", async ({ page }, text: string) => {
  await expect(assistant(page)).toContainText(text);
});

Then("the agent asks {string}", async ({ page }, question: string) => {
  await expect(page.getByRole("form", { name: "The agent asks" })).toContainText(question);
});

When("they answer {string}", async ({ page }, answer: string) => {
  const asked = page.getByRole("form", { name: "The agent asks" });
  await asked.getByRole("textbox", { name: "Answer" }).fill(answer);
  await asked.getByRole("button", { name: "Answer" }).click();
});

Then("the agent asks to run {string}", async ({ page }, tool: string) => {
  await expect(page.getByRole("region", { name: `Approve ${tool}?` })).toBeVisible();
});

When("they approve it", async ({ page }) => {
  await page.getByRole("button", { name: "Approve" }).click();
});

Then("they see the proposal {string}", async ({ page }, what: string) => {
  await expect(page.getByRole("region", { name: `Proposal: ${what}` })).toBeVisible();
});

When("they accept it", async ({ page }) => {
  await page.getByRole("button", { name: "Accept" }).click();
});

When("they reject it", async ({ page }) => {
  await page.getByRole("button", { name: "Reject" }).click();
});

Then("the proposal is {string}", async ({ page }, status: string) => {
  await expect(page.getByRole("region", { name: /^Proposal:/ })).toContainText(status);
});

When("they find the assistant's answer helpful", async ({ page }) => {
  await assistant(page).getByRole("button", { name: "Helpful", exact: true }).click();
});

Then("the answer shows them finding it helpful", async ({ page }) => {
  await expect(
    assistant(page).getByRole("button", { name: "Helpful", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});
