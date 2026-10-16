import { expect, type Page } from "@playwright/test";
import { choose } from "@portalr/ui/testing/bdd";
import { madeAs, Then, When } from "./fixtures";

/** A name made afresh for this run, so a scenario runs again against the same application. */
const fresh = (made: Map<string, string>, what: string) => {
  const name = `${what}-${crypto.randomUUID().slice(0, 8)}`;
  made.set(what, name);
  return name;
};

/** An item of a part of Access, by what it says, whether a table's row or a phone's card. */
const item = (page: Page, part: string, text: string) =>
  page
    .getByRole("table", { name: part })
    .getByRole("row")
    .or(page.getByRole("list", { name: part }).getByRole("listitem"))
    .filter({ hasText: text });

async function confirmed(page: Page, trigger: string | RegExp, action: string) {
  await page.getByRole("button", { name: trigger }).click();
  const dialog = page.getByRole("alertdialog");
  await dialog.getByRole("button", { name: action }).click();
  await expect(dialog).toHaveCount(0);
}

When("they open Access's {word}", async ({ page }, part: string) => {
  await page
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Access" })
    .click();
  await page.getByRole("navigation", { name: "Access" }).getByRole("link", { name: part }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Access");
});

When("they invite someone new", async ({ page, made }) => {
  const person = fresh(made, "invitee");
  await page.getByRole("textbox", { name: "Email" }).fill(`${person}@portalr.test`);
  await page.getByRole("button", { name: "Invite" }).click();
  await expect(page.getByRole("status")).toContainText(`${person}@portalr.test is invited`);
});

Then("the one they invited is a member", async ({ page, made }) => {
  await expect(item(page, "Members", madeAs(made, "invitee"))).toContainText("person");
});

When("they remove the one they invited", async ({ page, made }) => {
  const person = madeAs(made, "invitee");
  await confirmed(page, `Remove ${person}`, "Remove");
});

Then("the one they invited isn't a member", async ({ page, made }) => {
  await expect(item(page, "Members", madeAs(made, "invitee"))).toHaveCount(0);
});

When("they add a service principal", async ({ page, made }) => {
  await page.getByRole("textbox", { name: "Name" }).fill(fresh(made, "principal"));
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("is a service principal");
});

When("they issue it a key", async ({ page, made }) => {
  await choose(
    page,
    page.getByRole("combobox", { name: "Service principal" }),
    madeAs(made, "principal"),
  );
  await page.getByRole("button", { name: "Issue" }).click();
  await expect(page.getByRole("status")).toContainText("Copy it now");
  await expect(page.getByLabel("The key")).not.toHaveValue("");
});

Then("its key is listed, by its id alone", async ({ page, made }) => {
  const key = item(page, "Keys", madeAs(made, "principal"));
  await expect(key).toHaveCount(1);
  const secret = await page.getByLabel("The key").inputValue();
  await expect(key).not.toContainText(secret);
});

When("they revoke its key", async ({ page, made }) => {
  const key = item(page, "Keys", madeAs(made, "principal"));
  const trigger = await key.getByRole("button", { name: /^Revoke / }).textContent();
  await confirmed(page, trigger ?? "", "Revoke");
});

Then("it has no key", async ({ page, made }) => {
  await expect(item(page, "Keys", madeAs(made, "principal"))).toHaveCount(0);
});

When("they make a group of {string}", async ({ page, made }, member: string) => {
  await page.getByRole("textbox", { name: "Group" }).fill(fresh(made, "group"));
  // Each member is named with their kind beside them, such as "bob (person)".
  await page.getByRole("checkbox", { name: new RegExp(`^${member} \\(`) }).check();
  await page.getByRole("button", { name: "Create the group" }).click();
  await expect(page.getByRole("status")).toContainText("has 1 member.");
});

Then("the group is listed with {string}", async ({ page, made }, member: string) => {
  await expect(item(page, "Groups", madeAs(made, "group"))).toContainText(member);
});

When("they delete the group", async ({ page, made }) => {
  await confirmed(page, `Delete ${madeAs(made, "group")}`, "Delete");
});

Then("the group isn't listed", async ({ page, made }) => {
  await expect(item(page, "Groups", madeAs(made, "group"))).toHaveCount(0);
});

When("they create a role holding the first action the catalog lists", async ({ page, made }) => {
  await page.getByRole("textbox", { name: "Role" }).fill(fresh(made, "role"));
  await page.getByRole("region", { name: "Create a role" }).getByRole("checkbox").first().check();
  await page.getByRole("button", { name: "Create the role" }).click();
  await expect(page.getByRole("status")).toContainText("holds 1 action.");
});

Then("the role is listed", async ({ page, made }) => {
  await expect(item(page, "Custom roles", madeAs(made, "role"))).toHaveCount(1);
});

When("they delete the role", async ({ page, made }) => {
  await confirmed(page, `Delete ${madeAs(made, "role")}`, "Delete");
});

Then("the role isn't listed", async ({ page, made }) => {
  await expect(item(page, "Custom roles", madeAs(made, "role"))).toHaveCount(0);
});

When(
  "they grant it {string} on the workspace {string}",
  async ({ page, made }, role: string, workspace: string) => {
    const principal = madeAs(made, "principal");
    await choose(page, page.getByRole("combobox", { name: "Role" }), role);
    await choose(page, page.getByRole("combobox", { name: "On" }), "workspace");
    await page.getByRole("combobox", { name: "Workspace" }).fill(workspace);
    await choose(
      page,
      page.getByRole("combobox", { name: "To" }),
      `${principal} (service principal)`,
    );
    await page.getByRole("button", { name: "Grant", exact: true }).click();
    await expect(page.getByRole("status")).toContainText(`holds ${role} on workspace ${workspace}`);
  },
);

Then(
  "it holds {string} on the workspace {string}",
  async ({ page, made }, role: string, workspace: string) => {
    const grant = item(page, `Workspace ${workspace}`, madeAs(made, "principal"));
    await expect(grant).toHaveCount(1);
    // The workspace's own table holds it: the row needn't name the workspace again.
    await expect(grant).toContainText(role);
  },
);

When("they revoke its {string}", async ({ page, made }, role: string) => {
  const principal = madeAs(made, "principal");
  await confirmed(
    page,
    new RegExp(`^Revoke ${principal} \\(service principal\\) as ${role} `),
    "Revoke",
  );
});

Then("it holds no role", async ({ page, made }) => {
  await expect(item(page, "Workspace notes", madeAs(made, "principal"))).toHaveCount(0);
});

When("they look on a phone, at Access's Members", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  // On a phone the rail is behind the frame's Menu: the address opens it as directly.
  await page.goto("t/acme/access/members");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Access");
});

Then("the members are cards, and no table", async ({ page }) => {
  await expect(
    page.getByRole("list", { name: "Members" }).getByRole("listitem").first(),
  ).toBeVisible();
  await expect(page.getByRole("table", { name: "Members" })).toHaveCount(0);
});
