import { expect, type Page } from "@playwright/test";
import { Then, When } from "./fixtures";

const started = (thread: string | null) => {
  if (thread === null) {
    throw new Error("no thread was started: start one of their own first");
  }
  return thread;
};

/** The workspace's threads, once its log has been read: Start is enabled only then. */
async function threads(page: Page) {
  await expect(page.getByRole("button", { name: "Start" })).toBeEnabled();
  return page.getByRole("list", { name: "Threads" });
}

const dialog = (page: Page) => page.getByRole("dialog", { name: "Share the thread" });

async function act(page: Page, item: string) {
  await page.getByRole("button", { name: "Thread actions" }).click();
  await page.getByRole("menuitem", { name: item }).click();
}

When("they open the thread they started", async ({ page, scenario }) => {
  const thread = started(scenario.thread);
  await (await threads(page)).getByRole("link", { name: thread, exact: true }).click();
  await expect(page.getByRole("heading", { level: 2 })).toHaveText(thread);
});

Then("the thread they started isn't listed", async ({ page, scenario }) => {
  const thread = started(scenario.thread);
  await expect(page.getByRole("button", { name: "Start" })).toBeEnabled();
  await expect(page.getByRole("link", { name: thread, exact: true })).toHaveCount(0);
});

When("they restrict it", async ({ page }) => {
  await act(page, "Restrict");
  await expect(page.getByText("Restricted to the people it's shared with")).toBeVisible();
});

When("they lift its restriction", async ({ page }) => {
  await act(page, "Lift restriction");
  await expect(page.getByText("Restricted to the people it's shared with")).toHaveCount(0);
});

When("they share it with {string} as {word}", async ({ page }, person: string, role: string) => {
  await act(page, "Share…");
  const sharing = dialog(page);
  await sharing.getByRole("combobox", { name: "Person" }).selectOption(person);
  await sharing.getByRole("combobox", { name: "Role" }).selectOption(role);
  await sharing.getByRole("button", { name: "Share", exact: true }).click();
});

Then("{string} holds {word} on it", async ({ page }, person: string, role: string) => {
  await expect(
    dialog(page)
      .getByRole("list", { name: "People with access" })
      .getByRole("listitem", {
        name: `${person}, ${role}`,
      }),
  ).toBeVisible();
});

When("they revoke it", async ({ page }) => {
  await dialog(page).getByRole("button", { name: "Revoke" }).click();
});

Then("no one holds a role on it", async ({ page }) => {
  await expect(dialog(page).getByText("No one holds a role on it yet.")).toBeVisible();
});

When("they close the dialog", async ({ page }) => {
  await dialog(page).getByRole("button", { name: "Close" }).click();
});

Then("they can read it, and not post in it", async ({ page }) => {
  await expect(page.getByRole("heading", { level: 2 })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Message" })).toHaveCount(0);
});

Then("they have no thread actions", async ({ page }) => {
  await expect(page.getByRole("textbox", { name: "Message" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Thread actions" })).toHaveCount(0);
});
