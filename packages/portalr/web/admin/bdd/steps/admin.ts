import { expect, type Page } from "@playwright/test";
import { Given, Then, When } from "./fixtures";
import { email, password } from "./people";

async function signIn(page: Page, person: string) {
  await page.goto("sign-in");
  await page.getByLabel("Email").fill(email(person));
  await page.getByLabel("Password").fill(password(person));
  await page.getByRole("button", { name: "Sign in" }).click();
}

Given("{word} has signed in to admin", async ({ page }, person: string) => {
  await signIn(page, person);
  await expect(page.getByRole("button", { name: /^Account: / })).toBeVisible();
});

When("they open admin at {string}", async ({ page }, address: string) => {
  await page.goto(address.replace(/^\//, ""));
});

Then("they see the page {string}", async ({ page }, title: string) => {
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
});

Then("they're in {string}", async ({ page }, where: string) => {
  await expect(page.getByRole("button", { name: `Tenant: ${where}` })).toBeVisible();
});

Then("the {string} card shows a figure", async ({ page }, title: string) => {
  const card = page.getByRole("region", { name: title });
  await expect(card.getByText("Reading…")).toHaveCount(0);
  await expect(card.getByText(/^\d+$/)).toBeVisible();
});

Then("the {string} card says {string}", async ({ page }, title: string, text: string) => {
  await expect(page.getByRole("region", { name: title })).toContainText(text);
});

Then("the areas are {string}", async ({ page }, areas: string) => {
  await expect(
    page.getByRole("navigation", { name: /^(Tenant|Deployment)$/ }).getByRole("link"),
  ).toHaveText(areas.split(", "));
});

Then("the tenant switch offers {string}", async ({ page }, offered: string) => {
  await page.getByRole("button", { name: /^Tenant: / }).click();
  const menu = page.getByRole("menu");
  for (const choice of offered.split(", ")) {
    await expect(
      menu.getByRole(/All tenants/.test(choice) ? "menuitem" : "menuitemradio", {
        name: choice,
      }),
    ).toBeVisible();
  }
  await page.keyboard.press("Escape");
});
