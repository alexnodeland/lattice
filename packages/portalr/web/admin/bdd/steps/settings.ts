import { expect, type Page } from "@playwright/test";
import { Then, When } from "./fixtures";

When("they open Settings for the tenant", async ({ page }) => {
  await page
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Settings" })
    .click();
  const heading = page.getByRole("heading", { level: 1 });
  await expect(heading).toHaveText("Settings");
  await expect(heading).toBeFocused();
  await expect(page.getByRole("list", { name: "Settings on the tenant" })).toBeVisible();
});

When("they lower {string} to {int}", async ({ page }, name: string, value: number) => {
  await page.getByRole("textbox", { name }).fill(`${value}`);
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("status").filter({ hasText: `${name}: ${value} applies.` }),
  ).toBeVisible();
});

/** A setting's row, by its name. */
const rowOf = (page: Page, name: string) =>
  page.getByRole("listitem").filter({ has: page.getByRole("textbox", { name }) });

Then("{int} applies to {string}, set here", async ({ page }, value: number, name: string) => {
  await expect(rowOf(page, name).getByText(`Applies: ${value}.`)).toBeVisible();
  await expect(page.getByText(new RegExp(`^Set here to ${value} by `))).toBeVisible();
  await expect(page.getByRole("textbox", { name })).toHaveValue(`${value}`);
});

When("they try to raise {string} to {int}", async ({ page }, name: string, value: number) => {
  await page.getByRole("textbox", { name }).fill(`${value}`);
  await page.getByRole("button", { name: "Save FreeCAD's tries an hour" }).click();
});

Then("they are told it may be at most {int}, the default", async ({ page }, ceiling: number) => {
  await expect(
    page.getByRole("textbox", { name: "FreeCAD's tries an hour" }),
  ).toHaveAccessibleDescription(
    new RegExp(`it may be at most ${ceiling} here, as the deployment set it\\.`),
  );
});

When("they set {string} back to the default", async ({ page }, name: string) => {
  await page.getByRole("button", { name: `Use the default for ${name}` }).click();
  await expect(page.getByRole("status").filter({ hasText: `${name}: ` })).toBeVisible();
});

Then("{int} applies to {string}", async ({ page }, value: number, name: string) => {
  await expect(rowOf(page, name).getByText(`Applies: ${value}.`)).toBeVisible();
});

When(
  "they uncheck {string} in {string} and save",
  async ({ page }, tool: string, setting: string) => {
    await page.getByRole("group", { name: setting }).getByRole("checkbox", { name: tool }).click();
    await page.getByRole("button", { name: `Save ${setting}` }).click();
    await expect(page.getByRole("status").filter({ hasText: `${setting}: ` })).toBeVisible();
  },
);

Then("{string} is unchecked in {string}", async ({ page }, tool: string, setting: string) => {
  const box = page.getByRole("group", { name: setting }).getByRole("checkbox", { name: tool });
  await expect(box).not.toBeChecked();
});

Then("{string} is checked in {string}", async ({ page }, tool: string, setting: string) => {
  const box = page.getByRole("group", { name: setting }).getByRole("checkbox", { name: tool });
  await expect(box).toBeChecked();
});
