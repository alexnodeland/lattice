import { expect, type Page } from "@playwright/test";
import { Then, When } from "./fixtures";

const rail = (page: Page) => page.getByRole("navigation", { name: "Deployment" });

When("they open Tools", async ({ page }) => {
  await rail(page).getByRole("link", { name: "Tools" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Tools");
});

Then("they are told the tools are outside portalr's gates", async ({ page }) => {
  const notice = page.getByRole("complementary", {
    name: "These tools are outside portalr's gates",
  });
  await expect(notice).toBeVisible();
  await expect(notice).toContainText("outside the gates that Traces and Logs");
  await expect(notice).toContainText("Links made here are recorded");
});

When(
  "they ask for the links of the trace {string} and the tenant {string}",
  async ({ page }, trace: string, tenant: string) => {
    await page.getByRole("textbox", { name: "Trace id" }).fill(trace);
    await page.getByRole("combobox", { name: "Tenant" }).selectOption(tenant);
    await page.getByRole("button", { name: "Get links" }).click();
  },
);

Then("they get links into Grafana for the trace and for the tenant", async ({ page }) => {
  for (const name of [
    "The trace in Grafana, from Tempo",
    "The tenant's logs in Grafana, from Loki",
    "The tenant's traces in Grafana, from Tempo",
  ]) {
    const link = page.getByRole("link", { name });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", /^https?:\/\/[^/]+\/explore\?left=/);
    await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  }
});

Then("they are told Langfuse isn't configured here", async ({ page }) => {
  await expect(page.getByText("Langfuse isn't configured here, so it has no links.")).toBeVisible();
});

Then("no link is a script and no key is on the page", async ({ page }) => {
  const hrefs = await page
    .getByRole("link")
    .evaluateAll((links) => links.map((link) => link.getAttribute("href") ?? ""));
  expect(hrefs.filter((href) => /^\s*(javascript|data|vbscript):/i.test(href))).toEqual([]);
  const text = (await page.content()).toLowerCase();
  for (const secret of ["sk-lf", "pk-lf", "master_key", "secret_key"]) {
    expect(text).not.toContain(secret);
  }
});
