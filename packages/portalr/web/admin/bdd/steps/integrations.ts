import { expect } from "@playwright/test";
import { choose } from "@portalr/ui/testing/bdd";
import { email } from "../../../app/bdd/steps/people";
import { Then, When } from "./fixtures";

When("they open Integrations for the workspace {string}", async ({ page }, workspace: string) => {
  await page
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Integrations" })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Integrations");
  await choose(page, page.getByRole("combobox", { name: "Where" }), `Workspace ${workspace}`);
  await expect(page.getByRole("table", { name: `Integrations in ${workspace}` })).toBeVisible();
});

When("they turn {string} off", async ({ page }, name: string) => {
  const integration = page.getByRole("switch", { name });
  await expect(integration).toBeChecked();
  await integration.focus();
  await page.keyboard.press("Space");
  await expect(page.getByRole("status")).toContainText(`${name} is off`);
});

Then("{string} is off, set here", async ({ page }, name: string) => {
  const integration = page.getByRole("switch", { name });
  await expect(integration).not.toBeChecked();
  await expect(integration).toHaveAccessibleDescription("Off Set here");
});

When("they open the audit log, filtered to integrations switched", async ({ page }) => {
  await page
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Audit" })
    .click();
  await choose(page, page.getByRole("combobox", { name: "Change" }), "Integrations switched");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(/type=integration_set/);
});

Then(
  "the log says {word} turned {string} off in workspace {string}",
  async ({ page }, person: string, key: string, workspace: string) => {
    const change = `turned ${key} off in workspace ${workspace}`;
    const row = page
      .getByRole("table", { name: "Audit log" })
      .getByRole("row")
      .filter({
        has: page.getByRole("rowheader", { name: change }),
      });
    await expect(row.first()).toContainText(`${email(person)} (person)`);
  },
);
