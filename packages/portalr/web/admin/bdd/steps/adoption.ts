import { expect } from "@playwright/test";
import { Then, When } from "./fixtures";

When("they open Adoption", async ({ page }) => {
  await page
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Adoption" })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Adoption");
});

Then("it says product analytics aren't configured", async ({ page }) => {
  await expect(page.getByText("Product analytics aren't configured")).toBeVisible();
});
