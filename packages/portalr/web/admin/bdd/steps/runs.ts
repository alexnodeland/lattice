import { type APIRequestContext, expect, type Page } from "@playwright/test";
import { email, password } from "../../../app/bdd/steps/people";
import { Given, Then, When } from "./fixtures";

const origin = () => new URL(process.env.PORTALR_APP_URL ?? "http://localhost:8000").origin;

/** The workspace the scenarios' runs are in, in acme. */
const NOTES = "/reflexr/v1/workspaces/notes";

async function token(request: APIRequestContext, person: string): Promise<string> {
  const signed = await request.post(`${origin()}/auth/v1/token?grant_type=password`, {
    data: { email: email(person), password: password(person) },
  });
  expect(signed.ok()).toBe(true);
  return ((await signed.json()) as { access_token: string }).access_token;
}

/** Publish a ticket as a person, and wait for the run of triage it sets off: its id. */
Given("bob has published a ticket that fails in acme", async ({ request, made }) => {
  const headers = { Authorization: `Bearer ${await token(request, "bob")}`, "X-Tenant": "acme" };
  // artifactr lists a workspace once something is made in it, and Runs picks among the listed:
  // so a thread is made first, which no other scenario need have done.
  const thread = await request.post(`${origin()}/artifactr/v1/workspaces/notes/commands`, {
    headers,
    data: {
      type: "command",
      command_id: crypto.randomUUID(),
      command: {
        type: "create_thread",
        thread_id: `thr_${crypto.randomUUID().replaceAll("-", "")}`,
        title: "Runs",
      },
    },
  });
  expect(thread.ok()).toBe(true);
  const published = await request.post(`${origin()}${NOTES}/events`, {
    headers,
    data: { event: { type: "portalr:ticket.opened", subject: `fail ${crypto.randomUUID()}` } },
  });
  expect(published.ok()).toBe(true);
  const [{ seq }] = (await published.json()) as [{ seq: number }];
  let run: string | undefined;
  await expect
    .poll(async () => {
      // triage's own: a stored rule another scenario installed may match the ticket too.
      const read = await request.get(`${origin()}${NOTES}/runs`, {
        headers,
        params: { rule: "portalr:triage" },
      });
      const runs = (await read.json()) as { id: string; matched: number[] }[];
      run = runs.find((each) => each.matched.includes(seq))?.id;
      return run;
    })
    .toBeDefined();
  made.set("run", run as string);
});

const runOf = (page: Page, made: Map<string, string>) =>
  page
    .getByRole("table", { name: "Rules' runs" })
    .getByRole("row", { name: `Run ${made.get("run")}` });

When("they open Runs", async ({ page }) => {
  await page
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Runs" })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Runs");
  await page.getByRole("combobox", { name: "Workspace" }).selectOption("notes");
});

Then("the run is {string}", async ({ page, made }, status: string) => {
  // The run dead-letters after its attempts; the stream tells the page when it has.
  await expect(runOf(page, made).getByRole("status")).toHaveText(status, { timeout: 45_000 });
});

Then("the run has no history", async ({ page, made }) => {
  // The row is there, so that none is a finding and not an empty page.
  await expect(runOf(page, made)).toBeVisible();
  await expect(runOf(page, made).getByText(/^History \(/)).toHaveCount(0);
});

When("they ask to retry the run but think better of it", async ({ page, made }) => {
  await runOf(page, made)
    .getByRole("button", { name: `Retry run ${made.get("run")}` })
    .click();
  const dialog = page.getByRole("alertdialog", { name: "Retry this run?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
});

When("they retry the run, confirming", async ({ page, made }) => {
  await runOf(page, made)
    .getByRole("button", { name: `Retry run ${made.get("run")}` })
    .click();
  await page
    .getByRole("alertdialog", { name: "Retry this run?" })
    .getByRole("button", { name: "Retry the run" })
    .click();
});

Then("the run shows a history of {int}", async ({ page, made }, count: number) => {
  await expect(runOf(page, made).getByText(`History (${count})`)).toBeVisible({ timeout: 20_000 });
});

/** Skip or cancel a run, with a reason. */
async function intervene(
  page: Page,
  made: Map<string, string>,
  verb: "Skip" | "Cancel",
  reason: string,
) {
  await runOf(page, made)
    .getByRole("button", { name: `${verb} run ${made.get("run")}` })
    .click();
  const dialog = page.getByRole("alertdialog", { name: `${verb} this run?` });
  await dialog.getByRole("textbox", { name: "Reason (optional)" }).fill(reason);
  await dialog.getByRole("button", { name: `${verb} the run` }).click();
  await expect(dialog).toHaveCount(0);
}

When("they skip the run, saying {string}", async ({ page, made }, reason: string) => {
  await intervene(page, made, "Skip", reason);
});

When("they cancel the run, saying {string}", async ({ page, made }, reason: string) => {
  await intervene(page, made, "Cancel", reason);
});

Then("the run is no longer among those that need someone", async ({ page, made }) => {
  // The stream has delivered the runs: that none is this one is a finding, not a page still reading.
  await expect(page.getByRole("status").filter({ hasText: "Reading" })).toHaveCount(0);
  await expect(runOf(page, made)).toHaveCount(0);
});

When("they show every state", async ({ page }) => {
  await page.getByRole("combobox", { name: "Show" }).selectOption("all");
});

Then("the run's history says {string}", async ({ page, made }, reason: string) => {
  await runOf(page, made)
    .getByText(/^History \(/)
    .click();
  await expect(runOf(page, made).getByText(reason)).toBeVisible();
});

Then("they are told that a dead-lettered run failed every attempt", async ({ page }) => {
  await expect(page.getByText(/rule's run that failed every attempt/)).toBeVisible();
});
