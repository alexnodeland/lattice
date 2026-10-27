import { expect, type Page } from "@playwright/test";
import { Then, When } from "./fixtures";
import { proposedTo } from "./threads";

const kept = (note: string | null): string => {
  if (note === null) {
    throw new Error("no note was kept: keep the one the assistant proposed an edit to first");
  }
  return note;
};

/**
 * The proposal on the kept note, among the workspace's, by the link to it: named by the note's
 * title, as the artifacts' list names it, and leading to its page by its id.
 */
const proposalOn = (page: Page, note: string) =>
  page
    .getByRole("region", { name: /^Proposal:/ })
    .filter({ has: page.locator(`a[href$="/artifacts/${note}"]`) });

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
  // The list names a note by its title, and links to its page by its id; it doesn't show the id.
  const link = page
    .getByRole("list", { name: "Artifacts" })
    .locator(`a[href$="/artifacts/${note}"]`);
  const title = (await link.innerText()).trim();
  expect(title).not.toBe(note);
  await link.click();
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  // Its page shows the id, beside the kind and the version.
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
  const note = kept(scenario.note);
  const proposal = proposalOn(page, note);
  await expect(proposal.getByRole("button", { name: "Reject" })).toBeEnabled();
  // Its link names the note by its title, not its id.
  await expect(proposal.locator(`a[href$="/artifacts/${note}"]`)).not.toHaveText(note);
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
  // The state stands in for the page, so the focus starts on its heading.
  await expect(page.getByRole("heading", { name: "Artifact not found" })).toBeFocused({
    timeout: 2000,
  });
});

/** The artifact's thumbs are items of its actions menu, checked as given (portalr ADR-0080). */
When("they find the note helpful", async ({ page }) => {
  await artifactPage(page).getByRole("button", { name: "Artifact actions" }).click();
  await page.getByRole("menuitemcheckbox", { name: "Helpful" }).click();
});

Then("the note shows them finding it helpful", async ({ page }) => {
  await artifactPage(page).getByRole("button", { name: "Artifact actions" }).click();
  await expect(page.getByRole("menuitemcheckbox", { name: "Helpful" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await page.keyboard.press("Escape");
});
