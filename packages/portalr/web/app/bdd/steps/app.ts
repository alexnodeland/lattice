import { expect, type Page } from "@playwright/test";
import { Given, Then, When } from "./fixtures";
import { password, signIn } from "./people";

When("{word} signs in", async ({ page }, person: string) => {
  await signIn(page, person, password(person));
});

/** The account's menu, which holds signing out: every signed-in screen has it. */
export const account = (page: Page) => page.getByRole("button", { name: /^Account: / });

Given("{word} has signed in", async ({ page }, person: string) => {
  await signIn(page, person, password(person));
  await expect(account(page)).toBeVisible();
});

When(
  "{word} signs in with the password {string}",
  async ({ page }, person: string, secret: string) => {
    await signIn(page, person, secret);
  },
);

When("they choose the tenant {string}", async ({ page }, tenant: string) => {
  await page
    .getByRole("navigation", { name: "Tenants" })
    .getByRole("link", { name: tenant })
    .click();
});

When("they open the workspace {string}", async ({ page }, workspace: string) => {
  await page
    .getByRole("list", { name: "Workspaces" })
    .getByRole("link", { name: workspace, exact: true })
    .click();
});

When("they go back to every workspace in {string}", async ({ page }, tenant: string) => {
  await page.getByRole("button", { name: /^Workspace: / }).click();
  await page.getByRole("menuitem", { name: `Every workspace in ${tenant}` }).click();
});

When("they sign out", async ({ page }) => {
  await account(page).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
});

Then("they are in the workspace {string}", async ({ page }, workspace: string) => {
  await expect(page.getByRole("button", { name: /^Workspace: / })).toHaveAccessibleName(
    new RegExp(`, ${workspace}$`),
  );
});

Then("they see the page {string}", async ({ page }, title: string) => {
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
});

Then(
  "they see the workspaces {string} and {string}",
  async ({ page }, one: string, other: string) => {
    // Each workspace is a row whose title is a link with its name; the links to its areas are at
    // the row's end, in a list of their own.
    const workspaces = page
      .getByRole("list", { name: "Workspaces" })
      .locator(":scope > li > div:first-child a");
    await expect(workspaces).toHaveText([one, other]);
  },
);

Then("they see the workspace {string}", async ({ page }, workspace: string) => {
  await expect(
    page
      .getByRole("list", { name: "Workspaces" })
      .getByRole("link", { name: workspace, exact: true }),
  ).toBeVisible();
});

Then("each links to its areas", async ({ page }) => {
  for (const workspace of ["notes", "plans"]) {
    const areas = page.getByRole("list", { name: `${workspace}'s areas` }).getByRole("link");
    await expect(areas).toHaveText(["Threads", "Artifacts", "Proposals", "Runs", "Rules"]);
  }
});

When(
  "they open the {string} of the workspace {string}",
  async ({ page }, area: string, workspace: string) => {
    await page
      .getByRole("list", { name: `${workspace}'s areas` })
      .getByRole("link", { name: area })
      .click();
  },
);

Then("they see {string}", async ({ page }, text: string) => {
  await expect(page.getByText(text)).toBeVisible();
});

Then("they are told {string}", async ({ page }, text: string) => {
  await expect(page.getByLabel("Password")).toHaveAccessibleDescription(text);
});
