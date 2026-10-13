import { expect, type Page } from "@playwright/test";
import { Given, Then, When } from "./fixtures";
import { email, password } from "./people";

export async function signIn(page: Page, person: string, secret: string) {
  await page.goto("sign-in");
  await page.getByLabel("Email").fill(email(person));
  await page.getByLabel("Password").fill(secret);
  await page.getByRole("button", { name: "Sign in" }).click();
}

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
    .getByRole("navigation", { name: "Workspaces" })
    .getByRole("link", { name: workspace })
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
    const workspaces = page.getByRole("navigation", { name: "Workspaces" }).getByRole("link");
    await expect(workspaces).toHaveText([one, other]);
  },
);

Then("they see {string}", async ({ page }, text: string) => {
  await expect(page.getByText(text)).toBeVisible();
});

Then("they are told {string}", async ({ page }, text: string) => {
  await expect(page.getByLabel("Password")).toHaveAccessibleDescription(text);
});
