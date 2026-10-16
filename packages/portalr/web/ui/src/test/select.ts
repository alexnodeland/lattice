import { expect } from "vitest";
import { page, userEvent } from "vitest/browser";

/** Somewhere to find a select by its role, such as the page or a rendered screen or dialog. */
interface Scope {
  getByRole: typeof page.getByRole;
}

/** The list of choices is open, and then gone: it floats in a portal, so it is found on the page. */
const opened = () => expect.element(page.getByRole("option").first()).toBeVisible();
const closed = () => expect.element(page.getByRole("listbox")).not.toBeInTheDocument();

/** The words of every choice a select offers, in order, found by opening it and closing it again. */
export async function optionsOf(scope: Scope, name: string | RegExp): Promise<(string | null)[]> {
  await scope.getByRole("combobox", { name }).click();
  await opened();
  const words = page
    .getByRole("option")
    .elements()
    .map((option) => option.textContent);
  await userEvent.keyboard("{Escape}");
  await closed();
  return words;
}

/**
 * Choose from a select as a person does: open it by its name, then pick the choice by its words.
 * The choices float in a portal, so they are found on the page, not in the scope.
 */
export async function choose(scope: Scope, name: string | RegExp, option: string) {
  await scope.getByRole("combobox", { name }).click();
  await opened();
  await page.getByRole("option", { name: option, exact: true }).click();
  await closed();
}
