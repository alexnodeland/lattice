import { expect, type Page } from "@playwright/test";
import { Then, When } from "./fixtures";

/** The account menu's switch, which every signed-in screen has. */
async function switchIn(page: Page, on: boolean) {
  await page.getByRole("button", { name: /^Account: / }).click();
  const item = page.getByRole("menuitemcheckbox", { name: "Colour-blind friendly charts" });
  await expect(item).toHaveAttribute("aria-checked", String(!on));
  await item.click();
}

When("they turn colour-blind friendly charts on", async ({ page }) => {
  await switchIn(page, true);
});

When("they turn colour-blind friendly charts off", async ({ page }) => {
  await switchIn(page, false);
});

When("they reload the page", async ({ page }) => {
  await page.reload();
});

Then("the charts are colour-blind friendly", async ({ page }) => {
  await expect(page.locator("html")).toHaveAttribute("data-cvd", "");
});

Then("the charts are not colour-blind friendly", async ({ page }) => {
  await expect(page.locator("html")).not.toHaveAttribute("data-cvd");
});
