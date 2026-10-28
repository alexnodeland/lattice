/**
 * Diagrams' steps: one the assistant proposes and a person accepts, shown in the thread as its
 * card, and opened on its canvas, the add-on loaded then, under the portal's policy, with nothing
 * asked of another origin (portalr ADR-0072).
 */

import { expect, type Page } from "@playwright/test";
import { Then, When } from "./fixtures";
import { signIn } from "./people";
import { posted } from "./threads";

/** A diagram's card in the thread: in its log, or, from 1100 pixels, beside it (portalr ADR-0087). */
const card = (page: Page, name: string) => page.getByRole("main").getByRole("listitem", { name });

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
    // A save made on the canvas is read again once it is on the log: within seconds.
    await expect(card(page, name).getByText(`Diagram · ${count} elements`)).toBeVisible({
      timeout: 15_000,
    });
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

const canvasOf = (page: Page) => page.locator(".excalidraw canvas").last();

When("they edit it, and draw a rectangle", async ({ page }) => {
  const dialog = page.getByRole("dialog", { name: "Stack" });
  await dialog.getByRole("button", { name: "Edit" }).click();
  const box = await canvasOf(page).boundingBox();
  if (box === null) throw new Error("the canvas isn't drawn");
  // A click on an empty place first, so the canvas has the keyboard.
  await page.mouse.click(box.x + box.width - 200, box.y + box.height - 160);
  await page.keyboard.press("r");
  await page.mouse.move(box.x + box.width - 200, box.y + box.height - 160);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width - 80, box.y + box.height - 80, { steps: 5 });
  await page.mouse.up();
});

Then("the canvas says {string}", async ({ page }, said: string) => {
  const dialog = page.getByRole("dialog", { name: "Stack" });
  await expect(dialog.getByRole("status")).toHaveText(said, { timeout: 15_000 });
});

When("they paste the image {string} on it", async ({ page }, name: string) => {
  // An 8 by 8 red PNG, made on the page, pasted on the canvas as a file is.
  const uploading = page.waitForResponse((response) =>
    /\/diagrams\/[^/]+\/images$/.test(response.url()),
  );
  await page.evaluate(async (named) => {
    const drawing = document.createElement("canvas");
    drawing.width = 8;
    drawing.height = 8;
    const context = drawing.getContext("2d") as CanvasRenderingContext2D;
    context.fillStyle = "#c00";
    context.fillRect(0, 0, 8, 8);
    const png = await new Promise<Blob>((done) => drawing.toBlob((blob) => done(blob as Blob)));
    const pasted = new DataTransfer();
    pasted.items.add(new File([png], named, { type: "image/png" }));
    const target = document.querySelector(".excalidraw") as HTMLElement;
    target.dispatchEvent(
      new ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData: pasted }),
    );
  }, name);
  // Uploaded as the person; their next save, within the five seconds between saves, names it.
  const uploaded = await uploading;
  expect(uploaded.status()).toBe(201);
  // Put on the canvas, it is waiting to be saved, within the five seconds between saves.
  const dialog = page.getByRole("dialog", { name: "Stack" });
  await expect(dialog.getByRole("status")).toHaveText("Saving…");
});

Then(
  "the canvas asked nothing of another origin, and its policy refused nothing",
  async ({ page }) => {
    const watched = seen.get(page);
    const origin = new URL(page.url()).origin;
    expect(
      watched?.requests.filter(
        (url) => !url.startsWith(origin) && !url.startsWith("data:") && !url.startsWith("blob:"),
      ),
    ).toEqual([]);
    expect(watched?.violations).toEqual([]);
  },
);

Then("the canvas offers no way to give an element a link", async ({ page }) => {
  const dialog = page.getByRole("dialog", { name: "Stack" });
  // The image just put on it is selected, with its actions shown: no link among them.
  await expect(dialog.getByRole("button", { name: "Duplicate" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: /link/i })).toHaveCount(0);
  await page.keyboard.press("ControlOrMeta+k");
  await expect(dialog.getByRole("textbox", { name: /link/i })).toHaveCount(0);
});

When("they close the canvas", async ({ page }) => {
  await page
    .getByRole("dialog", { name: "Stack" })
    .getByRole("button", { name: "Close canvas" })
    .click();
});

Then(
  "the canvas draws its image, read from the portal, under the portal's policy",
  async ({ page }) => {
    const watched = seen.get(page);
    // Its image's bytes, read as the person, from the diagrams' route on the portal's origin.
    await expect
      .poll(() => watched?.requests.some((url) => /\/images\/[0-9a-f]{64}$/.test(url)))
      .toBe(true);
    await expect(page.locator(".excalidraw canvas").first()).toBeVisible();
    const origin = new URL(page.url()).origin;
    expect(
      watched?.requests.filter(
        (url) => !url.startsWith(origin) && !url.startsWith("data:") && !url.startsWith("blob:"),
      ),
    ).toEqual([]);
    expect(watched?.violations).toEqual([]);
  },
);

When("they open the diagram's page", async ({ page }) => {
  await card(page, "Stack").getByRole("link", { name: "Open its page" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Stack" })).toBeVisible();
});

Then(
  "its versions {int} and {int} are by {string}",
  async ({ page }, first: number, second: number, who: string) => {
    const revisions = page.getByRole("list", { name: "Revisions" });
    for (const version of [first, second]) {
      await expect(revisions.getByRole("listitem", { name: `Version ${version}` })).toContainText(
        `by ${who}`,
      );
    }
  },
);

When("they open the thread {string}", async ({ page }, title: string) => {
  await page.getByRole("link", { name: title, exact: true }).first().click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
});

Then("the canvas offers no edit", async ({ page }) => {
  const dialog = page.getByRole("dialog", { name: "Stack" });
  // Its grants are asked as the canvas opens: once they have answered, Edit isn't there.
  const asked = page.waitForResponse((response) => response.url().endsWith("/grantr/v1/checks"), {
    timeout: 3_000,
  });
  await expect(page.locator(".excalidraw canvas").first()).toBeVisible();
  await asked.catch(() => undefined);
  await expect(dialog.getByRole("button", { name: "Edit" })).toHaveCount(0);
});

/** The window a second person opened the same canvas in, beside the first's. */
const beside = new WeakMap<Page, Page>();

When(
  "{word} opens it in the thread {string}, in a window of their own",
  async ({ page }, person: string, thread: string) => {
    const browser = page.context().browser();
    if (browser === null) throw new Error("no browser to open a second window in");
    const context = await browser.newContext({
      baseURL: new URL("/portalr/app/", page.url()).href,
    });
    const other = await context.newPage();
    beside.set(page, other);
    await signIn(other, person);
    await other
      .getByRole("list", { name: "Workspaces" })
      .getByRole("link", { name: "notes", exact: true })
      .click();
    await other.getByRole("link", { name: thread, exact: true }).first().click();
    await card(other, "Stack").getByRole("button", { name: "Open canvas" }).click();
    await expect(other.locator(".excalidraw canvas").first()).toBeVisible();
  },
);

Then("the canvas says {string} is here", async ({ page }, name: string) => {
  const here = page.getByRole("dialog", { name: "Stack" }).getByRole("list", { name: "Here now" });
  await expect(here).toContainText(name, { timeout: 10_000 });
});

Then("their canvas says {string} is here", async ({ page }, name: string) => {
  const other = beside.get(page);
  if (other === undefined) throw new Error("no one opened it beside them");
  const here = other.getByRole("dialog", { name: "Stack" }).getByRole("list", { name: "Here now" });
  await expect(here).toContainText(name, { timeout: 10_000 });
});

When("the other window closes", async ({ page }) => {
  await beside.get(page)?.context().close();
});

Then("the canvas says no one else is here", async ({ page }) => {
  const dialog = page.getByRole("dialog", { name: "Stack" });
  await expect(dialog.getByRole("list", { name: "Here now" })).toHaveCount(0, { timeout: 15_000 });
});
