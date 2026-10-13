import { expect } from "@playwright/test";
import { Then, When } from "./fixtures";

When("they open Feedback", async ({ page }) => {
  await page
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Feedback" })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Feedback");
});

Then("it says Langfuse isn't configured", async ({ page }) => {
  await expect(page.getByText("Langfuse isn't configured")).toBeVisible();
});
