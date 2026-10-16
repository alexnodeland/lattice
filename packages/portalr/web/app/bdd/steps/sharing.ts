import { expect, type Page } from "@playwright/test";
import { account } from "./app";
import { started, Then, When } from "./fixtures";
import { email, password, signIn } from "./people";

/** The workspace's threads, once its log has been read: Start is enabled only then. */
async function threads(page: Page) {
  await expect(page.getByRole("button", { name: "Start" })).toBeEnabled();
  return page.getByRole("list", { name: "Threads" });
}

const dialog = (page: Page) => page.getByRole("dialog", { name: "Share the thread" });

/** Who holds a role on the thread, in its sharing dialog, by what the item says: their email. */
const holder = (page: Page, person: string, role: string) =>
  dialog(page)
    .getByRole("list", { name: "People with access" })
    .getByRole("listitem")
    .filter({ hasText: `${email(person)} ${role}` });

async function act(page: Page, item: string) {
  await page.getByRole("button", { name: "Thread actions" }).click();
  await page.getByRole("menuitem", { name: item }).click();
}

async function restrict(page: Page) {
  await act(page, "Restrict");
  await expect(page.getByText("Restricted to the people it's shared with")).toBeVisible();
}

When("they open the thread they started", async ({ page, scenario }) => {
  const thread = started(scenario.thread);
  await (await threads(page)).getByRole("link", { name: thread, exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(thread);
});

When("they open the thread they started by its address", async ({ page, scenario }) => {
  await page.goto(started(scenario.threadUrl));
});

Then("the thread they started isn't listed", async ({ page, scenario }) => {
  const thread = started(scenario.thread);
  await expect(page.getByRole("button", { name: "Start" })).toBeEnabled();
  await expect(page.getByRole("link", { name: thread, exact: true })).toHaveCount(0);
});

When("they restrict it", async ({ page }) => {
  await restrict(page);
});

When("they lift its restriction", async ({ page }) => {
  await act(page, "Lift restriction");
  await expect(page.getByText("Restricted to the people it's shared with")).toHaveCount(0);
});

When(
  "alice restricts it in a window of her own, while they have it open",
  async ({ browser, baseURL, scenario }) => {
    const other = await browser.newContext({ baseURL: started(baseURL ?? null, "set a baseURL") });
    try {
      const alice = await other.newPage();
      await signIn(alice, "alice", password("alice"));
      await expect(account(alice)).toBeVisible();
      await alice.goto(started(scenario.threadUrl));
      await restrict(alice);
    } finally {
      await other.close();
    }
  },
);

When("they open its sharing", async ({ page }) => {
  await act(page, "Share…");
  await expect(dialog(page)).toBeVisible();
});

When("they share it with {string} as {word}", async ({ page }, person: string, role: string) => {
  await act(page, "Share…");
  const sharing = dialog(page);
  await sharing.getByRole("combobox", { name: "Person" }).selectOption(person);
  await sharing.getByRole("combobox", { name: "Role" }).selectOption(role);
  await sharing.getByRole("button", { name: "Share", exact: true }).click();
});

Then("{string} holds {word} on it", async ({ page }, person: string, role: string) => {
  await expect(holder(page, person, role)).toBeVisible();
});

Then(
  "they're offered {string}, and not {string}",
  async ({ page }, offered: string, not: string) => {
    const people = dialog(page).getByRole("combobox", { name: "Person" });
    // The dialog shows a person by their email, which the test application gives everyone.
    await expect(people.getByRole("option", { name: email(offered), exact: true })).toHaveCount(1);
    await expect(people.getByRole("option", { name: email(not), exact: true })).toHaveCount(0);
  },
);

When("they revoke {string}'s {word}", async ({ page }, person: string, role: string) => {
  await holder(page, person, role).getByRole("button", { name: "Revoke" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Revoke the role" }).click();
});

Then("no one holds a role on it", async ({ page }) => {
  await expect(dialog(page).getByText("No one holds a role on it yet.")).toBeVisible();
});

When("they close the dialog", async ({ page }) => {
  await dialog(page).getByRole("button", { name: "Close" }).click();
  await expect(page.getByRole("button", { name: "Thread actions" })).toBeFocused();
});

Then("they can read it, and not post in it", async ({ page, scenario }) => {
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(started(scenario.thread));
  await expect(page.getByRole("textbox", { name: "Message" })).toHaveCount(0);
});

Then("they have no thread actions", async ({ page, scenario }) => {
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(started(scenario.thread));
  await expect(page.getByRole("button", { name: "Thread actions" })).toHaveCount(0);
});

When("they try to post {string}", async ({ page }, message: string) => {
  await page.getByRole("textbox", { name: "Message" }).fill(message);
  await page.getByRole("button", { name: "Send" }).click();
});

Then("they're told it isn't available to them any more", async ({ page }) => {
  await expect(page.getByRole("alert")).toHaveText("This isn't available to you any more.");
  await expect(page.getByRole("textbox", { name: "Message" })).toHaveCount(0);
});
