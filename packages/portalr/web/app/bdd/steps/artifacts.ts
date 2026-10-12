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
  await page.getByRole("navigation", { name: "Workspace" }).getByRole("link", { name }).click();
  await expect(page.getByRole("heading", { level: 2 })).toHaveText(name);
});

When("they open the note", async ({ page, scenario }) => {
  const note = kept(scenario.note);
  await page.getByRole("list", { name: "Artifacts" }).getByRole("link", { name: note }).click();
  await expect(page.getByRole("heading", { level: 2 })).toHaveText(note);
});

Then("the note reads {string}", async ({ page, scenario }, text: string) => {
  const note = page.getByRole("region", { name: kept(scenario.note) });
  await expect(note.getByRole("paragraph").filter({ hasText: /^Launch/ })).toHaveText(text);
});

Then(
  "its latest revision removed {string} and added {string}",
  async ({ page }, removed: string, added: string) => {
    const latest = page.getByRole("list", { name: "Revisions" }).getByRole("listitem").first();
    await expect(latest.locator("del")).toHaveText(`removed: ${removed}`);
    await expect(latest.locator("ins")).toHaveText(`added: ${added}`);
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
