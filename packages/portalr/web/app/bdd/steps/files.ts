/**
 * Native files' steps: a document the assistant drafts, read on its artifact's page, where its
 * pages are drawn from `data:` URLs under the app's own policy, and downloaded (portalr ADR-0048).
 */

import { expect, type Page } from "@playwright/test";
import type { DataTable } from "playwright-bdd";
import { started, Then, When } from "./fixtures";
import { posted } from "./threads";

const DOCUMENT = "keep the document the assistant drafted";

/** The document's own section of its page. */
const file = (page: Page) => page.getByRole("region", { name: "The file" });

When("they keep the document the assistant drafted", async ({ page, scenario }) => {
  const answer = posted(page, "Assistant");
  await expect(answer).toContainText("Drafted");
  scenario.document =
    /Drafted (art_[0-9a-f]+)/.exec((await answer.textContent()) ?? "")?.[1] ?? null;
  started(scenario.document, DOCUMENT);
});

When("they open the document", async ({ page, scenario }) => {
  await page.goto(`t/acme/w/notes/artifacts/${started(scenario.document, DOCUMENT)}`);
  await expect(file(page)).toBeVisible();
});

Then("its outline reads:", async ({ page }, lines: DataTable) => {
  await expect(page.getByRole("region", { name: "Outline" }).getByRole("listitem")).toHaveText(
    lines.raw().flat(),
  );
});

Then("its first page of {int} is drawn", async ({ page }, pages: number) => {
  const drawn = file(page).getByRole("img", { name: `Page 1 of ${pages}` });
  await expect(drawn).toBeVisible();
  // Drawn, not refused: an image the policy blocked has no width.
  await expect
    .poll(() => drawn.evaluate((image: HTMLImageElement) => image.naturalWidth))
    .toBeGreaterThan(0);
});

Then("it is available to check out", async ({ page }) => {
  await expect(file(page).getByRole("status")).toHaveText("Available to check out");
});

When("they download it", async ({ page, scenario }) => {
  const saved = page.waitForEvent("download");
  await file(page).getByRole("button", { name: "Download" }).click();
  scenario.downloaded = (await saved).suggestedFilename();
});

Then("they have {string}", ({ scenario }, name: string) => {
  expect(scenario.downloaded).toBe(name);
});
