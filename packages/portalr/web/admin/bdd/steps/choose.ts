import type { Locator, Page } from "@playwright/test";

/** Choose from a select as a person does: open it, then pick the choice by its words. */
export async function choose(page: Page, select: Locator, option: string) {
  await select.click();
  await page.getByRole("option", { name: option, exact: true }).click();
}
