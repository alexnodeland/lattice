import { expect } from "@playwright/test";
import { Then, When } from "./fixtures";

When("they open Usage", async ({ page }) => {
  await page
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Usage" })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Usage");
});

Then("it says LiteLLM isn't configured", async ({ page }) => {
  await expect(page.getByText("LiteLLM isn't configured")).toBeVisible();
});
