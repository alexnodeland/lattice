import type { Locator, Page } from "playwright";

/** The list of choices has been opened: it floats in a portal, so it is found on the page. */
const listbox = (page: Page) => page.getByRole("listbox");

/** Choose from a select as a person does: open it, then pick the choice by its words. */
export async function choose(page: Page, select: Locator, option: string) {
  await select.click();
  await page.getByRole("option", { name: option, exact: true }).click();
  await listbox(page).waitFor({ state: "detached" });
}

/** The words of every choice a select offers, found by opening it and closing it again. */
export async function optionsOf(page: Page, select: Locator): Promise<string[]> {
  await select.click();
  await page.getByRole("option").first().waitFor();
  const words = await page.getByRole("option").allTextContents();
  await page.keyboard.press("Escape");
  await listbox(page).waitFor({ state: "detached" });
  return words;
}
