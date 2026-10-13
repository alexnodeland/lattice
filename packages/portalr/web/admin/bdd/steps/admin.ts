import { type APIRequestContext, expect, type Page } from "@playwright/test";
import { email, password, signIn } from "../../../app/bdd/steps/people";
import { Given, Then, When } from "./fixtures";

const origin = () => new URL(process.env.PORTALR_APP_URL ?? "http://localhost:8000").origin;

Given("{word} has signed in to admin", async ({ page }, person: string) => {
  await signIn(page, person);
  await expect(page.getByRole("button", { name: /^Account: / })).toBeVisible();
});

When("they open admin at {string}", async ({ page }, address: string) => {
  await page.goto(address.replace(/^\//, ""));
});

When("they open admin again", async ({ page }) => {
  await page.goto("./");
});

When("they choose {string}", async ({ page }, tenant: string) => {
  await page
    .getByRole("navigation", { name: "Tenants" })
    .getByRole("link", { name: tenant })
    .click();
});

Then("they see the page {string}", async ({ page }, title: string) => {
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
});

Then("they're in {string}", async ({ page }, where: string) => {
  await expect(page.getByRole("button", { name: `Tenant: ${where}` })).toBeVisible();
});

/** A card of Home, by its title. */
const card = (page: Page, title: string) => page.getByRole("article", { name: title });

Then("the {string} card shows a figure", async ({ page }, title: string) => {
  await expect(card(page, title)).toHaveAttribute("aria-busy", "false");
  await expect(card(page, title).getByText(/^[\d,]+\+?$/)).toBeVisible();
});

Then("the {string} card says {string}", async ({ page }, title: string, text: string) => {
  await expect(card(page, title)).toContainText(text);
});

Then("the areas are {string}", async ({ page }, areas: string) => {
  await expect(
    page.getByRole("navigation", { name: /^(Tenant|Deployment)$/ }).getByRole("link"),
  ).toHaveText(areas.split(", "));
});

Then("the tenant switch offers {string}", async ({ page }, offered: string) => {
  await page.getByRole("button", { name: /^Tenant: / }).click();
  const menu = page.getByRole("menu");
  await expect(menu.getByRole("menuitemradio")).toHaveText(offered.split(", "));
  await page.keyboard.press("Escape");
});

When("they switch to {string}", async ({ page }, tenant: string) => {
  await page.getByRole("button", { name: /^Tenant: / }).click();
  await page.getByRole("menu").getByRole("menuitemradio", { name: tenant }).click();
});

/** A person's access token, as Supabase Auth issues it at the application's `/auth/v1`. */
async function token(request: APIRequestContext, person: string): Promise<string> {
  const signed = await request.post(`${origin()}/auth/v1/token?grant_type=password`, {
    data: { email: email(person), password: password(person) },
  });
  expect(signed.ok()).toBe(true);
  return ((await signed.json()) as { access_token: string }).access_token;
}

/** Post in a thread of its own, as `person`, and wait for its turn to end. */
async function posted(request: APIRequestContext, bearer: string, thread: string, text: string) {
  const headers = { Authorization: `Bearer ${bearer}`, "X-Tenant": "acme" };
  const command = (command: Record<string, unknown>) =>
    request.post(`${origin()}/artifactr/v1/workspaces/notes/commands`, {
      headers,
      data: { type: "command", command_id: crypto.randomUUID(), command },
    });
  expect((await command({ type: "post_message", thread_id: thread, content: text })).ok()).toBe(
    true,
  );
}

Given("bob has had a turn fail in acme", async ({ request }) => {
  const bearer = await token(request, "bob");
  const thread = `thr_${crypto.randomUUID().replaceAll("-", "")}`;
  const created = await request.post(`${origin()}/artifactr/v1/workspaces/notes/commands`, {
    headers: { Authorization: `Bearer ${bearer}`, "X-Tenant": "acme" },
    data: {
      type: "command",
      command_id: crypto.randomUUID(),
      command: { type: "create_thread", thread_id: thread, title: "A failing thread" },
    },
  });
  expect(created.ok()).toBe(true);
  // A turn that completes first, so the failed series is exported at zero before it rises:
  // a series' first sample is no increase to Prometheus (artifactr ADR-0067).
  await posted(request, bearer, thread, "hello");
  await new Promise((resolve) => setTimeout(resolve, 3_000));
  await posted(request, bearer, thread, "fail now");
});

Then("the {string} card eventually counts at least one", async ({ page }, title: string) => {
  await expect
    .poll(
      async () => {
        await page.reload();
        await expect(card(page, title)).toHaveAttribute("aria-busy", "false");
        const shown = await card(page, title)
          .getByText(/^[\d,]+\+?$/)
          .textContent();
        return Number((shown ?? "0").replaceAll(/[,+]/g, ""));
      },
      { timeout: 25_000, intervals: [2_000] },
    )
    .toBeGreaterThanOrEqual(1);
});
