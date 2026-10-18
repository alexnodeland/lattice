/**
 * Native files' steps: a document the assistant drafts, read on its artifact's page, where its
 * pages are drawn from `data:` URLs under the app's own policy, and downloaded; checked out, which
 * opens the hosted editor on an origin of its own, and checked in, as the stand-in for WordCraft
 * reads files (portalr ADR-0048, ADR-0049, ADR-0050).
 */

import { expect, type Page } from "@playwright/test";
import type { DataTable } from "playwright-bdd";
import { started, Then, When } from "./fixtures";
import { posted } from "./threads";

const DOCUMENT = "keep the document the assistant drafted";

/** The brief as the assistant drafts it, paragraph by paragraph. */
const BRIEF = ["Brief", "Brief starts on Monday.", "Who comes.", "What to bring."];

/** The document's own section of its page. */
const file = (page: Page) => page.getByRole("region", { name: "The file" });

/** A file of the stand-in for WordCraft, as a person saves one from it: its paragraphs, as JSON. */
const saved = (paragraphs: readonly string[]) => ({
  name: "brief.docx",
  mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  buffer: Buffer.from(JSON.stringify({ paragraphs, comments: [], saves: 1 })),
});

When("they keep the document the assistant drafted", async ({ page, scenario }) => {
  const answer = posted(page, "Assistant");
  await expect(answer).toContainText("Drafted");
  scenario.document =
    /Drafted (art_[0-9a-f]+)/.exec((await answer.textContent()) ?? "")?.[1] ?? null;
  started(scenario.document, DOCUMENT);
  scenario.threadUrl = page.url();
});

When("they open the document", async ({ page, scenario }) => {
  await page.goto(`t/acme/w/notes/artifacts/${started(scenario.document, DOCUMENT)}`);
  await expect(file(page)).toBeVisible();
});

When("they ask the assistant to revise the document", async ({ page, scenario }) => {
  await page.goto(started(scenario.threadUrl, DOCUMENT));
  const message = `revise ${started(scenario.document, DOCUMENT)}`;
  // Counted, since the same request may have been posted before.
  const mine = page.getByRole("log", { name: "Messages" }).getByRole("listitem", { name: "You" });
  // Once the thread has been read: it holds the assistant's answers so far.
  await expect(posted(page, "Assistant")).toBeVisible();
  const before = await mine.count();
  await page.getByRole("textbox", { name: "Message" }).fill(message);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(mine).toHaveCount(before + 1);
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
  // Who has it, among what else the section says.
  await expect(
    file(page)
      .getByRole("status")
      .filter({ hasText: /^Available to check out$/ }),
  ).toBeVisible();
});

Then("it is checked out by them", async ({ page }) => {
  await expect(
    file(page)
      .getByRole("status")
      .filter({ hasText: /^Checked out by you until/ }),
  ).toBeVisible();
});

When("they download it", async ({ page, scenario }) => {
  const download = page.waitForEvent("download");
  await file(page).getByRole("button", { name: "Download", exact: true }).click();
  scenario.downloaded = (await download).suggestedFilename();
});

Then("they have {string}", ({ scenario }, name: string) => {
  expect(scenario.downloaded).toBe(name);
});

/** The hosted editor's address, which the scenarios' script names. */
const editorUrl = () => {
  const url = process.env.PORTALR_EDITOR_URL;
  if (!url) {
    throw new Error("PORTALR_EDITOR_URL names no editor: run the scenarios through scripts/bdd");
  }
  return url;
};

When("they check it out", async ({ page, scenario }) => {
  const origin = new URL(editorUrl()).origin;
  // What any page on the editor's origin asks for and what its policy refuses, heard on the
  // context from before the editor opens, so its first request and message aren't missed.
  const seen = { requests: [] as string[], violations: [] as string[] };
  page.context().on("request", (request) => {
    // A navigation's frame isn't there yet: the portal's own are its download, the editor's its
    // page, which the editor's own address shows, as it shows if it navigates anywhere else.
    if (!request.isNavigationRequest() && request.frame().page() !== page) {
      seen.requests.push(request.url());
    }
  });
  page.context().on("console", (message) => {
    if (
      message.page()?.url().startsWith(origin) &&
      message.text().includes("Content Security Policy")
    ) {
      seen.violations.push(message.text());
    }
  });
  const opened = page.waitForEvent("popup");
  const download = page.waitForEvent("download");
  await file(page).getByRole("button", { name: "Check out and open WordCraft" }).click();
  const editor = await opened;
  scenario.editor = { page: editor, ...seen };
  scenario.downloaded = (await download).suggestedFilename();
  await expect(editor).toHaveURL(editorUrl());
});

Then(
  "the editor opened in a tab of its own, and called nothing out",
  async ({ page, scenario }) => {
    const editor = scenario.editor;
    if (editor === null) {
      throw new Error("no editor opened: check the document out first");
    }
    // Its own script ran, and compiled its own WebAssembly, under its own policy.
    await expect(editor.page.locator("#state")).toHaveText("Ready");
    const origin = new URL(editor.page.url()).origin;
    const portal = new URL(page.url()).origin;
    expect(origin).not.toBe(portal);
    const loaded = await editor.page.evaluate(() =>
      performance.getEntriesByType("resource").map((entry) => entry.name),
    );
    expect([...editor.requests, ...loaded].filter((url) => new URL(url).origin !== origin)).toEqual(
      [],
    );
    expect(editor.violations).toEqual([]);
    // And it can't: asked to reach the portal, its policy refuses, and says so.
    const reached = await editor.page.evaluate(
      (to) =>
        fetch(to).then(
          () => "reached",
          () => "refused",
        ),
      `${portal}/portalr/config.json`,
    );
    expect(reached).toBe("refused");
    await expect.poll(() => editor.violations.length).toBeGreaterThan(0);
  },
);

const checkIn = async (page: Page, now: string, was: string) => {
  const paragraphs = BRIEF.map((paragraph) => (paragraph === was ? now : paragraph));
  await file(page).getByLabel("The edited file").setInputFiles(saved(paragraphs));
  await file(page).getByRole("button", { name: "Check in" }).click();
};

When(
  "they check in the brief with {string} for {string}",
  async ({ page }, now: string, was: string) => {
    await checkIn(page, now, was);
  },
);

When(
  "they check in the brief with {string} for {string}, but the answer never comes",
  async ({ page }, now: string, was: string) => {
    // The server takes the file and answers; the browser is told the connection dropped.
    await page.route("**/checkouts/*/file", async (route) => {
      await route.fetch();
      await route.abort("connectionreset");
    });
    await checkIn(page, now, was);
    await expect(file(page).getByRole("alert")).toBeVisible();
    await page.unroute("**/checkouts/*/file");
  },
);

When("they send it again", async ({ page }) => {
  await file(page).getByRole("button", { name: "Try again" }).click();
});

Then("the file says {string}", async ({ page }, text: string) => {
  await expect(file(page)).toContainText(text);
});

Then("its latest version is {int}", async ({ page }, version: number) => {
  await page.reload();
  await expect(page.getByText(`word_document, version ${version}`)).toBeVisible();
});

When("they accept the assistant's proposal there", async ({ page }) => {
  const proposal = page.getByRole("region", { name: /^Proposal:/ });
  await expect(proposal).toContainText("You have the file checked out");
  await proposal.getByRole("button", { name: "Accept" }).click();
  await expect(page.getByText("word_document, version 2")).toBeVisible();
});

Then(
  "the check-in is a proposal there, with its pages beside version {int}'s",
  async ({ page }, version: number) => {
    const proposal = page
      .getByRole("region", { name: /^Proposal:/ })
      .filter({ hasText: "A check-in kept as a proposal" });
    await expect(proposal.getByRole("button", { name: "Accept" })).toBeEnabled();
    await proposal.getByText(`Compare with version ${version}`).click();
    const pages = proposal.getByRole("region", { name: "Its pages beside the head's" });
    await expect(pages.getByRole("img", { name: `Page 1, Version ${version}` })).toBeVisible();
    await expect(pages.getByRole("img", { name: "Page 1, Proposed" })).toBeVisible();
    await expect(proposal.getByRole("insertion")).toContainText("Everyone");
    await expect(pages.getByText("Changed", { exact: true }).first()).toBeVisible();
  },
);
