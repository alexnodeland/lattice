import { expect, type Page } from "@playwright/test";
import { Then, When } from "./fixtures";
import { proposedTo } from "./threads";

const kept = (note: string | null): string => {
  if (note === null) {
    throw new Error("no note was kept: keep the one the assistant proposed an edit to first");
  }
  return note;
};

/** The proposal on the kept note, among the workspace's, by the link to it. */
const proposalOn = (page: Page, note: string) =>
  page
    .getByRole("region", { name: /^Proposal:/ })
    .filter({ has: page.getByRole("link", { name: note, exact: true }) });

When("they keep the note the assistant proposed an edit to", async ({ page, scenario }) => {
  scenario.note = await proposedTo(page);
});

When("they open the workspace's {word}", async ({ page }, area: string) => {
  const name = area.charAt(0).toUpperCase() + area.slice(1);
  await page
    .getByRole("navigation", { name: "Workspace", exact: true })
    .getByRole("link", { name })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(name);
});

/** The artifact's page: the region its heading names, which holds its content and its actions. */
const artifactPage = (page: Page) =>
  page.getByRole("region").filter({ has: page.getByRole("heading", { level: 1 }) });

When("they open the note", async ({ page, scenario }) => {
  const note = kept(scenario.note);
  // The list names a note by its title, and gives its id beside it.
  const row = page
    .getByRole("list", { name: "Artifacts" })
    .getByRole("listitem")
    .filter({ hasText: note });
  const link = row.getByRole("link");
  const title = (await link.innerText()).trim();
  expect(title).not.toBe(note);
  await link.click();
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  // The id stays in view, beside the kind and the version.
  await expect(artifactPage(page).getByText(note)).toBeVisible();
});

Then("the note reads {string}", async ({ page }, text: string) => {
  // The note's own paragraph: its title, in the heading, may say the same.
  await expect(
    artifactPage(page).getByText(text, { exact: true }).and(page.locator("p")),
  ).toBeVisible();
});

Then(
  "its latest revision removed {string} and added {string}",
  async ({ page }, removed: string, added: string) => {
    const latest = page.getByRole("list", { name: "Revisions" }).getByRole("listitem").first();
    await expect(latest.getByRole("deletion")).toHaveText(`removed: ${removed}`);
    await expect(latest.getByRole("insertion")).toHaveText(`added: ${added}`);
  },
);

Then("the note's proposal is open there", async ({ page, scenario }) => {
  const proposal = proposalOn(page, kept(scenario.note));
  await expect(proposal.getByRole("button", { name: "Reject" })).toBeEnabled();
});

When("they reject the note's proposal there", async ({ page, scenario }) => {
  await proposalOn(page, kept(scenario.note)).getByRole("button", { name: "Reject" }).click();
});

Then("the note's proposal is {string} there", async ({ page, scenario }, status: string) => {
  await expect(proposalOn(page, kept(scenario.note))).toContainText(status);
});

When("they open an artifact that isn't there", async ({ page }) => {
  await page.goto("t/acme/w/notes/artifacts/art_0000000000000000");
});

Then("they are told it isn't found", async ({ page }) => {
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Artifact not found", {
    timeout: 2000,
  });
});

When("they find the note helpful", async ({ page }) => {
  await artifactPage(page).getByRole("button", { name: "Helpful", exact: true }).click();
});

Then("the note shows them finding it helpful", async ({ page }) => {
  await expect(
    artifactPage(page).getByRole("button", { name: "Helpful", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});
