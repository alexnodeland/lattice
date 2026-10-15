import { expect } from "@playwright/test";
import { Then, When } from "./fixtures";

When("they open Traces", async ({ page }) => {
  await page
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Traces" })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Traces");
});

Then("a trace is eventually listed", async ({ page }) => {
  // Tempo takes a moment to hold what the application just sent: read the list again until it does.
  await expect
    .poll(
      async () => {
        await page.reload();
        await expect(page.getByRole("heading", { level: 1 })).toHaveText("Traces");
        return page.getByRole("table", { name: "Traces" }).getByRole("link").count();
      },
      { timeout: 40_000, intervals: [2_000] },
    )
    .toBeGreaterThanOrEqual(1);
});

When("they open the newest trace", async ({ page }) => {
  await page.getByRole("table", { name: "Traces" }).getByRole("link").first().click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Trace");
});

Then("they see its spans as a tree", async ({ page }) => {
  const tree = page.getByRole("tree", { name: "Spans" });
  await expect(tree).toBeVisible();
  await expect(tree.getByRole("treeitem").first()).toBeVisible();
  // The first span is chosen, and its details are beside the tree.
  await expect(page.getByRole("region", { name: "Attributes" })).toBeVisible();
});

Then("what was said in them is kept out until asked for", async ({ page }) => {
  // The application doesn't record prompts or completions by default: nothing is withheld, so
  // nothing offers to be shown, and no span's attributes hold any.
  await expect(page.getByRole("button", { name: "Show what was said" })).toHaveCount(0);
  await expect(page.getByText("gen_ai.input.messages")).toHaveCount(0);
});
