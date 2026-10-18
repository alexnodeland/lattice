import { expect, type Page } from "@playwright/test";
import { Then, When } from "./fixtures";

/** Text as a regular expression matches it, its every character as written. */
const escaped = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** A field of the form the agent asks, by its label, which may also say it is required. */
const field = (page: Page, label: string) =>
  page.getByRole("textbox", { name: new RegExp(`^${escaped(label)}( \\(required\\))?$`) });

Then("the agent asks the form {string}", async ({ page }, title: string) => {
  await expect(page.getByRole("form", { name: title })).toBeVisible();
});

When("they fill in {string} with {string}", async ({ page }, label: string, text: string) => {
  await field(page, label).fill(text);
});

When("they send it with {string}", async ({ page }, button: string) => {
  await page.getByRole("button", { name: button }).click();
});

Then("{string} is refused with {string}", async ({ page }, label: string, refusal: string) => {
  const refused = field(page, label);
  await expect(refused).toHaveAttribute("aria-invalid", "true");
  await expect(refused).toHaveAccessibleDescription(new RegExp(`${escaped(refusal)}$`));
  await expect(refused).toBeFocused();
});
