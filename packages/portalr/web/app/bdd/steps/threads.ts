import { expect, type Page } from "@playwright/test";
import { createBdd } from "playwright-bdd";

const { Then, When } = createBdd();

/** Each message is named for who posted it: the reader's are "You", the agent's "Assistant". */
const posted = (page: Page, by: "You" | "Assistant") =>
  page
    .getByRole("log", { name: "Messages" })
    .getByRole("listitem", { name: by, exact: true })
    .last();

When("they start the thread {string}", async ({ page }, title: string) => {
  await page.getByLabel("New thread").fill(title);
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByRole("heading", { level: 2 })).toHaveText(title);
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

When("they answer {string}", async ({ page }, answer: string) => {
  const asked = page.getByRole("form", { name: "The agent asks" });
  await asked.getByRole("textbox", { name: "Answer" }).fill(answer);
  await asked.getByRole("button", { name: "Answer" }).click();
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
  // The agent names the note it proposed an edit to; artifactr's REST surface reads it, as the
  // signed-in person, in acme.
  await expect(posted(page, "Assistant")).toContainText("proposed an edit to");
  const said = (await posted(page, "Assistant").textContent()) ?? "";
  const note = /proposed an edit to (art_[0-9a-f]+)/.exec(said)?.[1];
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

When("they find the assistant's answer helpful", async ({ page }) => {
  await posted(page, "Assistant").getByRole("button", { name: "Helpful", exact: true }).click();
});

Then("the answer shows them finding it helpful", async ({ page }) => {
  await expect(
    posted(page, "Assistant").getByRole("button", { name: "Helpful", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});
