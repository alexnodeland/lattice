import { expect, type Page } from "@playwright/test";
import { Then, When } from "./fixtures";

/** Each message is named for who posted it: the reader's are "You", the agent's "Assistant". */
export const posted = (page: Page, by: "You" | "Assistant") =>
  page
    .getByRole("log", { name: "Messages" })
    .getByRole("listitem", { name: by, exact: true })
    .last();

When("they start the thread {string}", async ({ page }, title: string) => {
  await page.getByLabel("New thread").fill(title);
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
});

When("they post {string}", async ({ page }, message: string) => {
  await page.getByRole("textbox", { name: "Message" }).fill(message);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(posted(page, "You")).toContainText(message);
});

Then("the assistant says {string}", async ({ page }, text: string) => {
  await expect(posted(page, "Assistant")).toContainText(text);
});

Then("the agent asks {string}", async ({ page }, question: string) => {
  await expect(page.getByRole("form", { name: "The agent asks" })).toContainText(question);
});

/** An option of the agent's questions, by its label: a radio, which may be recommended, or a box. */
When("they choose {string}", async ({ page }, label: string) => {
  const asked = page.getByRole("form", { name: "The agent asks" });
  const choice = asked.getByRole("radio", { name: new RegExp(`^${label}( Recommended)?$`) });
  await ((await choice.count()) > 0
    ? choice
    : asked.getByRole("checkbox", { name: label })
  ).click();
});

When("they write {string}", async ({ page }, words: string) => {
  await page.getByRole("textbox", { name: "Your answer" }).fill(words);
});

When("they answer", async ({ page }) => {
  await page
    .getByRole("form", { name: "The agent asks" })
    .getByRole("button", { name: "Answer" })
    .click();
});

Then("the agent's questions say {string} was chosen", async ({ page }, label: string) => {
  const asked = page.getByRole("region", { name: "The agent asked" });
  await expect(asked.getByText(label, { exact: true })).toBeVisible();
});

Then("the thread says {int} turn(s) failed", async ({ page }, failed: number) => {
  await expect(
    page.getByRole("log", { name: "Messages" }).getByText("The assistant couldn't finish."),
  ).toHaveCount(failed);
});

When("they try it again", async ({ page }) => {
  await page.getByRole("button", { name: "Try again" }).click();
});

Then("the agent asks to run {string}", async ({ page }, tool: string) => {
  await expect(page.getByRole("region", { name: `Approve ${tool}?` })).toBeVisible();
});

When("they approve it", async ({ page }) => {
  await page.getByRole("button", { name: "Approve" }).click();
});

Then("they see the proposal {string}", async ({ page }, what: string) => {
  await expect(page.getByRole("region", { name: `Proposal: ${what}` })).toBeVisible();
});

When("they accept it", async ({ page }) => {
  await page.getByRole("button", { name: "Accept" }).click();
});

When("they reject it", async ({ page }) => {
  await page.getByRole("button", { name: "Reject" }).click();
});

Then("the proposal is {string}", async ({ page }, status: string) => {
  await expect(page.getByRole("region", { name: /^Proposal:/ })).toContainText(status);
});

Then("the note says {string}", async ({ page }, text: string) => {
  const note = await proposedTo(page);
  const read = await page.evaluate(async (id) => {
    const session = JSON.parse(localStorage.getItem("portalr") ?? "{}") as {
      access_token?: string;
    };
    const response = await fetch(`/artifactr/v1/workspaces/notes/artifacts/${id}`, {
      headers: { Authorization: `Bearer ${session.access_token}`, "X-Tenant": "acme" },
    });
    return ((await response.json()) as { data: { text: string } }).data.text;
  }, note);
  expect(read).toBe(text);
});

/** The note the agent says it proposed an edit to: it names its own (tests/app/notes.py). */
export async function proposedTo(page: Page): Promise<string> {
  const answer = posted(page, "Assistant");
  await expect(answer).toContainText("proposed an edit to");
  const note = /proposed an edit to (art_[0-9a-f]+)/.exec((await answer.textContent()) ?? "")?.[1];
  if (note === undefined) {
    throw new Error("the assistant named no note");
  }
  return note;
}

When("they find the assistant's answer helpful", async ({ page }) => {
  await posted(page, "Assistant").getByRole("button", { name: "Helpful", exact: true }).click();
});

Then("the answer shows them finding it helpful", async ({ page }) => {
  await expect(
    posted(page, "Assistant").getByRole("button", { name: "Helpful", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});
