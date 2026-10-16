import { expect } from "@playwright/test";
import { choose } from "./choose";
import { madeAs, Then, When } from "./fixtures";

When("they open the audit log, filtered to members added", async ({ page }) => {
  await page
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Audit" })
    .click();
  await choose(page, page.getByRole("combobox", { name: "Change" }), "Members added");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(/type=member_added/);
});

Then("the log says they added it", async ({ page, made }) => {
  // The log opens on its newest changes: theirs is among them.
  await expect(
    page
      .getByRole("table", { name: "Audit log" })
      .getByRole("rowheader", { name: `added ${madeAs(made, "principal")} (service principal)` }),
  ).toBeVisible();
});
