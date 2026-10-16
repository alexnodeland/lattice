import { expect } from "@playwright/test";
import { Then, When } from "./fixtures";

/** The operator's rail, on "All tenants". */
const rail = (page: import("@playwright/test").Page) =>
  page.getByRole("navigation", { name: "Deployment" });

When("they open Tenants", async ({ page }) => {
  await rail(page).getByRole("link", { name: "Tenants" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Tenants");
});

Then(
  "they see the tenants {string} and {string}",
  async ({ page }, first: string, second: string) => {
    const table = page.getByRole("table", { name: "Tenants" });
    await expect(table.getByRole("row", { name: new RegExp(`^${first}`) })).toBeVisible();
    await expect(table.getByRole("row", { name: new RegExp(`^${second}`) })).toBeVisible();
  },
);

When("they fill in a new tenant, owned by {string}", async ({ page, made }, email: string) => {
  const tenant = `bdd-${crypto.randomUUID().slice(0, 8)}`;
  made.set("tenant", tenant);
  await page.getByRole("textbox", { name: "Tenant" }).fill(tenant);
  await page.getByRole("textbox", { name: "Owner's email" }).fill(email);
});

When(
  "they fill in the same tenant again, owned by {string}",
  async ({ page, made }, email: string) => {
    await page.getByRole("textbox", { name: "Tenant" }).fill(made.get("tenant") ?? "");
    await page.getByRole("textbox", { name: "Owner's email" }).fill(email);
  },
);

When("they ask to create it", async ({ page }) => {
  await page.getByRole("button", { name: "Create tenant" }).click();
});

Then("they are asked to confirm creating it", async ({ page, made }) => {
  const dialog = page.getByRole("alertdialog", { name: `Create ${made.get("tenant")}?` });
  await expect(dialog).toBeVisible();
  // Asking made nothing: the tenant is not yet among them.
  await expect(
    page
      .getByRole("table", { name: "Tenants" })
      .getByRole("row", { name: new RegExp(`^${made.get("tenant")}`) }),
  ).toHaveCount(0);
});

When("they confirm", async ({ page }) => {
  await page.getByRole("alertdialog").getByRole("button", { name: "Create the tenant" }).click();
});

Then("the tenant is created, owned by {string}", async ({ page, made }, owner: string) => {
  await expect(
    page.getByText(`${made.get("tenant")} is created, owned by ${owner}.`),
  ).toBeVisible();
});

Then("the tenants include the new tenant", async ({ page, made }) => {
  await expect(
    page
      .getByRole("table", { name: "Tenants" })
      .getByRole("row", { name: new RegExp(`^${made.get("tenant")}`) }),
  ).toBeVisible();
});

Then("the owner's email is not on the page", async ({ page }) => {
  await expect(page.getByText("founder@portalr.test")).toHaveCount(0);
});

Then("they are told the tenant exists", async ({ page, made }) => {
  await expect(page.getByRole("alertdialog").getByRole("alert")).toHaveText(
    `Not created: ${made.get("tenant")} exists`,
  );
});

When("they open the deployment's Audit", async ({ page }) => {
  await rail(page).getByRole("link", { name: "Audit" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Audit");
});

Then("they see the deployment's audit log", async ({ page }) => {
  const table = page.getByRole("table", { name: "Deployment audit log" });
  await expect(table).toBeVisible();
  await expect(table.getByRole("row").nth(1)).toBeVisible();
});
