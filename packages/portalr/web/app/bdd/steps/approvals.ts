import { expect, type Page } from "@playwright/test";
import { Then, When } from "./fixtures";

/** The approvals waiting for the reader, one row each. */
const waiting = (page: Page) => page.getByRole("list", { name: "Approvals waiting for you" });

When("they open the tenant's approvals", async ({ page }) => {
  await page.getByRole("link", { name: "Approvals", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Approvals", level: 1 })).toBeVisible();
});

Then(
  "{string} waits for them, asked by the agent {word} for {word}",
  async ({ page }, title: string, agent: string, person: string) => {
    const row = waiting(page).getByRole("listitem").filter({ hasText: title });
    // A person is named by their email where the server names them.
    await expect(row).toContainText(
      new RegExp(`Asked by the agent ${agent} for ${person}\\S* in notes`),
    );
  },
);

When("they approve {string} because {string}", async ({ page }, title: string, why: string) => {
  await waiting(page).getByRole("link", { name: title }).click();
  await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
  await page.getByRole("textbox", { name: "Why" }).fill(why);
  await page.getByRole("button", { name: "Approve" }).click();
});

Then("it is approved by them, because {string}", async ({ page }, why: string) => {
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  await expect(page.getByText(/^you, /)).toBeVisible();
  await expect(page.getByText(why, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);
});

Then("{string} is theirs to confirm in admin", async ({ page }, title: string) => {
  const row = waiting(page).getByRole("listitem").filter({ hasText: title });
  await expect(row).toContainText("Yours to confirm, in admin.");
  await expect(row.getByRole("link", { name: title })).toHaveAttribute(
    "href",
    /^\/portalr\/admin\/confirm\/apr_/,
  );
});

When(
  "they confirm {string} in admin, typing {string}",
  async ({ page }, title: string, tenant: string) => {
    await waiting(page).getByRole("link", { name: title }).click();
    await expect(page.getByRole("heading", { name: `Confirm: ${title}`, level: 1 })).toBeVisible();
    await page.getByRole("textbox", { name: `Type ${tenant} to confirm` }).fill(tenant);
    await page.getByRole("button", { name: "Confirm" }).click();
  },
);

Then("it is approved by them on the confirm page", async ({ page }) => {
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  await expect(page.getByText(/^you, .*, on the confirm page$/)).toBeVisible();
});
