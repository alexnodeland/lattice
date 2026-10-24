/**
 * Diagrams' steps: one the assistant proposes and a person accepts, shown in the thread as its
 * card, and opened on its canvas, the add-on loaded then, under the portal's policy, with nothing
 * asked of another origin (portalr ADR-0072).
 */

import { expect, type Page } from "@playwright/test";
import { Then, When } from "./fixtures";
import { posted } from "./threads";

const card = (page: Page, name: string) =>
  page.getByRole("log", { name: "Messages" }).getByRole("listitem", { name });

/** What the page asks for, and what its policy refuses, from before the canvas opens. */
const seen = new WeakMap<Page, { requests: string[]; violations: string[] }>();

When("they accept the diagram the assistant proposed", async ({ page }) => {
  await expect(posted(page, "Assistant")).toContainText("Drew the stack.");
  const proposal = page.getByRole("region", { name: /^Proposal:/ });
  await proposal.getByRole("button", { name: "Accept" }).click();
  await expect(proposal).toContainText("Accepted");
});

Then(
  "the diagram {string} is shown with {int} elements",
  async ({ page }, name: string, count: number) => {
    await expect(card(page, name).getByText(`Diagram · ${count} elements`)).toBeVisible();
  },
);

Then("its text version reads {string}", async ({ page }, words: string) => {
  const shown = card(page, "Stack");
  await shown.getByRole("button", { name: "Text version" }).click();
  await expect(shown.getByText(new RegExp(words)).first()).toBeVisible();
});

When("they open its canvas", async ({ page }) => {
  const watched = { requests: [] as string[], violations: [] as string[] };
  page.on("request", (request) => watched.requests.push(request.url()));
  page.on("console", (message) => {
    if (message.text().includes("Content Security Policy")) watched.violations.push(message.text());
  });
  seen.set(page, watched);
  await card(page, "Stack").getByRole("button", { name: "Open canvas" }).click();
});

Then(
  "the canvas draws it, under the portal's policy, from the portal's origin alone",
  async ({ page }) => {
    const dialog = page.getByRole("dialog", { name: "Stack" });
    await expect(dialog.getByRole("button", { name: "Close canvas" })).toBeVisible();
    await expect(page.locator(".excalidraw canvas").first()).toBeVisible();
    const watched = seen.get(page);
    const origin = new URL(page.url()).origin;
    // Its faces are the portal's own copy, which the router serves beside the app.
    const face = await page.request.get(
      `${origin}/portalr/app/excalidraw/fonts/Virgil/Virgil-Regular.woff2`,
    );
    expect(face.status()).toBe(200);
    expect(
      watched?.requests.filter(
        (url) => !url.startsWith(origin) && !url.startsWith("data:") && !url.startsWith("blob:"),
      ),
    ).toEqual([]);
    expect(watched?.violations).toEqual([]);
  },
);

When("they press Escape", async ({ page }) => {
  await page.keyboard.press("Escape");
});

Then("the canvas is closed, and {string} has the focus", async ({ page }, name: string) => {
  await expect(page.locator(".excalidraw")).toHaveCount(0);
  await expect(page.getByRole("button", { name })).toBeFocused();
});
