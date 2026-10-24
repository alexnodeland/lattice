/**
 * A diagram's card and its canvas under portalr's Content-Security-Policy, in Chromium: the canvas
 * loaded only when opened, drawn with no violation of the policy, no WebAssembly, and no request to
 * any origin but the page's own; reached and left by the keyboard, its focus kept in it while it is
 * open and given back to the button that opened it (portalr ADR-0072, ADR-0068).
 */

import { type Browser, chromium, type Page } from "playwright";
import { afterAll, beforeAll, expect, test } from "vitest";
import { open } from "./harness";

let browser: Browser;

beforeAll(async () => {
  browser = await chromium.launch();
});

afterAll(() => browser.close());

/** Every request the page makes, and the ones to an origin but its own. */
function requests(page: Page, origin: string) {
  const made: string[] = [];
  page.on("request", (request) => made.push(request.url()));
  return {
    made,
    away: () =>
      made.filter(
        (url) => !url.startsWith(origin) && !url.startsWith("data:") && !url.startsWith("blob:"),
      ),
  };
}

test("the card loads no canvas until it is opened, and the canvas keeps to the policy", async () => {
  const { page, reported } = await open(browser);
  const origin = new URL(page.url()).origin;
  const seen = requests(page, origin);
  await page.goto(`${origin}/?diagram`);
  const opener = page.getByRole("button", { name: "Open canvas" });
  await opener.waitFor();
  expect(seen.made.filter((url) => /canvas/.test(url))).toEqual([]);
  // The text version is text: the label's markup is shown, never run.
  await page.getByRole("button", { name: "Text version" }).click();
  await expect.poll(() => page.getByText("<script>alert(1)</script>").count()).toBe(1);
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "Stack" });
  await dialog.waitFor();
  await page.locator(".excalidraw canvas").first().waitFor();
  // Its faces load, from the page's own copy of them.
  await expect
    .poll(() => seen.made.some((url) => url.startsWith(`${origin}/excalidraw/fonts/`)))
    .toBe(true);
  await page.evaluate(() => document.fonts.ready);
  await page.mouse.move(400, 300);
  await page.mouse.wheel(0, 200);
  expect(seen.made.some((url) => /canvas/.test(url))).toBe(true);
  expect(seen.away()).toEqual([]);
  expect(await reported()).toEqual([]);
  await page.context().close();
});

test("the canvas is reached and left by the keyboard, and gives the focus back", async () => {
  const { page, reported } = await open(browser, "?diagram");
  const opener = page.getByRole("button", { name: "Open canvas" });
  await opener.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Stack" });
  await dialog.waitFor();
  await page.locator(".excalidraw canvas").first().waitFor();
  expect(await dialog.getAttribute("aria-modal")).toBe("true");
  // Tab, however far, stays in the dialog.
  for (let step = 0; step < 25; step += 1) {
    await page.keyboard.press("Tab");
    expect(
      await page.evaluate(() => document.activeElement?.closest("[role=dialog]") !== null),
    ).toBe(true);
  }
  for (let step = 0; step < 5; step += 1) {
    await page.keyboard.press("Shift+Tab");
    expect(
      await page.evaluate(() => document.activeElement?.closest("[role=dialog]") !== null),
    ).toBe(true);
  }
  // Escape leaves it, with nothing selected on the canvas, and the focus is the opener's again.
  await page.keyboard.press("Escape");
  await dialog.waitFor({ state: "detached" });
  expect(await page.evaluate(() => document.activeElement?.textContent)).toBe("Open canvas");
  // And so does its Close button.
  await page.keyboard.press("Enter");
  await dialog.waitFor();
  await dialog.getByRole("button", { name: "Close canvas" }).click();
  await dialog.waitFor({ state: "detached" });
  expect(await page.evaluate(() => document.activeElement?.textContent)).toBe("Open canvas");
  expect(await reported()).toEqual([]);
  await page.context().close();
});

/** What the page keeps in its storage: localStorage's keys, and IndexedDB's databases. */
const stored = (page: Page) =>
  page.evaluate(async () => ({
    local: Object.keys(localStorage).sort(),
    indexed: (await indexedDB.databases()).map((each) => each.name).sort(),
  }));

test("a hostile diagram's links, pages and images open nothing and ask for nothing", async () => {
  const { page, reported } = await open(browser, "?diagram=hostile");
  const origin = new URL(page.url()).origin;
  const seen = requests(page, origin);
  const windows: string[] = [];
  page.context().on("page", (opened) => windows.push(opened.url()));
  await page.getByRole("button", { name: "Open canvas" }).click();
  await page.locator(".excalidraw canvas").first().waitFor();
  // A click on each place an element was, and on its link's icon, if one were drawn.
  for (const [x, y] of [
    [300, 330],
    [520, 430],
    [300, 650],
    [900, 150],
    [470, 330],
  ]) {
    await page.mouse.click(x as number, y as number);
  }
  expect(await page.locator("iframe").count()).toBe(0);
  expect(
    await page.locator(".excalidraw-hyperlinkContainer, .excalidraw__embeddable").count(),
  ).toBe(0);
  expect(windows).toEqual([]);
  expect(seen.away()).toEqual([]);
  expect(await reported()).toEqual([]);
  await page.context().close();
});

test("the canvas stays in view mode: no shortcut, drop or paste opens anything or stores anything", async () => {
  const { page, reported } = await open(browser, "?diagram");
  const origin = new URL(page.url()).origin;
  const seen = requests(page, origin);
  const before = await stored(page);
  await page.getByRole("button", { name: "Open canvas" }).click();
  const dialog = page.getByRole("dialog", { name: "Stack" });
  await page.locator(".excalidraw canvas").first().waitFor();
  await page
    .locator(".excalidraw canvas")
    .last()
    .click({ position: { x: 50, y: 50 } });
  const chooser: string[] = [];
  page.on("filechooser", () => chooser.push("a file dialog"));
  for (const keys of [
    "?",
    "Shift+?",
    "Control+/",
    "Meta+/",
    "Control+s",
    "Meta+s",
    "Control+o",
    "Control+Shift+e",
    "Control+k",
    "Meta+k",
    "Control+Shift+p",
    "Alt+/",
  ]) {
    await page.keyboard.press(keys);
  }
  // A file dropped, and text and an image pasted, on the canvas.
  await page.evaluate(() => {
    const target = document.querySelector(".excalidraw") as HTMLElement;
    const moved = new DataTransfer();
    moved.items.add(new File([new Uint8Array([137, 80, 78, 71])], "x.png", { type: "image/png" }));
    for (const type of ["dragover", "drop"]) {
      target.dispatchEvent(
        new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: moved }),
      );
    }
    const pasted = new DataTransfer();
    pasted.setData("text/plain", "https://example.com/");
    pasted.items.add(new File(["<svg/>"], "x.svg", { type: "image/svg+xml" }));
    target.dispatchEvent(
      new ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData: pasted }),
    );
  });
  await page.waitForTimeout(300);
  expect(await page.getByRole("dialog").count()).toBe(1);
  await expect.poll(() => dialog.isVisible()).toBe(true);
  expect(await page.locator(".HelpDialog, .command-palette-dialog, .Modal").count()).toBe(0);
  expect(await page.getByRole("link").count()).toBe(0);
  expect(chooser).toEqual([]);
  expect(seen.away()).toEqual([]);
  expect(await stored(page)).toEqual(before);
  expect(await reported()).toEqual([]);
  await page.context().close();
});

test("a diagram written badly is mended where it can be, and what can't be is said", async () => {
  const { page, reported } = await open(browser, "?diagram=broken");
  await page.getByRole("button", { name: "Open canvas" }).click();
  const dialog = page.getByRole("dialog", { name: "Broken" });
  await page.locator(".excalidraw canvas").first().waitFor();
  // Restore can't mend the arrow and the line with no points, and a text with no words is none:
  // three. The rectangle placed out of reach is drawn at the origin, the ellipse with no id given one.
  await expect
    .poll(() => dialog.getByRole("status").textContent())
    .toMatch(/^3 elements not drawn here/);
  expect(await reported()).toEqual([]);
  await page.context().close();
});

test("the canvas zooms by its own buttons from the keyboard", async () => {
  const { page, reported } = await open(browser, "?diagram");
  await page.getByRole("button", { name: "Open canvas" }).click();
  const dialog = page.getByRole("dialog", { name: "Stack" });
  await page.locator(".excalidraw canvas").first().waitFor();
  const zoomIn = dialog.getByRole("button", { name: "Zoom in" });
  const level = dialog.getByRole("button", { name: "Reset zoom" });
  const before = await level.textContent();
  await zoomIn.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => level.textContent()).not.toBe(before);
  const after = await level.textContent();
  await zoomIn.focus();
  await page.keyboard.press(" ");
  await expect.poll(() => level.textContent()).not.toBe(after);
  expect(await reported()).toEqual([]);
  await page.context().close();
});

test("the text version is there to describe the canvas while its disclosure is closed", async () => {
  const { page } = await open(browser, "?diagram");
  const opener = page.getByRole("button", { name: "Open canvas" });
  const about = await opener.getAttribute("aria-describedby");
  expect(about).not.toBeNull();
  expect(
    await page.evaluate((id) => document.getElementById(id ?? "")?.textContent ?? "", about),
  ).toContain('Diagram "Stack"');
  await page.context().close();
});

test("Enter and Space on every control of the canvas open nothing and store nothing", async () => {
  const { page, reported } = await open(browser, "?diagram");
  const origin = new URL(page.url()).origin;
  const seen = requests(page, origin);
  const before = await stored(page);
  // The card's count is the description's.
  const counted = await page.getByText(/^Diagram · \d+ elements$/).textContent();
  const described = await page.evaluate(() => document.querySelector("pre")?.textContent ?? "");
  expect(described).toContain(`: ${/(\d+) elements/.exec(counted ?? "")?.[1]} elements`);
  await page.getByRole("button", { name: "Open canvas" }).click();
  await page.locator(".excalidraw canvas").first().waitFor();
  // Excalidraw's menu and help, which lead out of view mode, aren't there to reach.
  for (const hidden of [".main-menu-trigger", ".help-icon"]) {
    for (const found of await page.locator(hidden).all()) {
      expect(await found.isVisible()).toBe(false);
    }
  }
  const controls = page.locator(
    ".excalidraw button, .excalidraw [role=button], .excalidraw [tabindex]:not([tabindex='-1'])",
  );
  const count = await controls.count();
  expect(count).toBeGreaterThan(0);
  for (let at = 0; at < count; at += 1) {
    for (const key of ["Enter", " "]) {
      const control = controls.nth(at);
      if (await control.isVisible()) {
        await control.focus();
        await page.keyboard.press(key);
      }
    }
  }
  expect(
    await page.locator(".HelpDialog, .Modal, .popover, .sidebar, .dropdown-menu").count(),
  ).toBe(0);
  expect(await page.getByRole("dialog").count()).toBe(1);
  expect(seen.away()).toEqual([]);
  expect(await stored(page)).toEqual(before);
  expect(await reported()).toEqual([]);
  await page.context().close();
});

/** What the page's host was sent: each edit, and the type of each image uploaded. */
const sent = (page: Page) =>
  page.evaluate(() => window.canvasSent) as Promise<{
    commits: { baseVersion: number; ops: { op: string; path: string }[]; summary: string }[];
    uploads: string[];
  }>;

test("a person edits on the canvas: what they draw, and an image they paste, is sent as their edit", async () => {
  const { page, reported } = await open(browser, "?diagram=edit");
  const origin = new URL(page.url()).origin;
  const seen = requests(page, origin);
  await page.getByRole("button", { name: "Open canvas" }).click();
  const dialog = page.getByRole("dialog", { name: "Stack" });
  await page.locator(".excalidraw canvas").first().waitFor();
  await dialog.getByRole("button", { name: "Edit" }).click();
  // A rectangle drawn: its tool's key, and a drag.
  await page
    .locator(".excalidraw canvas")
    .last()
    .click({ position: { x: 600, y: 600 } });
  await page.keyboard.press("r");
  await page.mouse.move(600, 500);
  await page.mouse.down();
  await page.mouse.move(700, 580, { steps: 5 });
  await page.mouse.up();
  await expect.poll(async () => (await sent(page)).commits.length, { timeout: 8000 }).toBe(1);
  const [drawn] = (await sent(page)).commits;
  expect(drawn?.baseVersion).toBe(1);
  expect(drawn?.ops.map((op) => op.op)).toEqual(["add"]);
  expect(drawn?.summary).toBe("1 element changed on the canvas");
  // The rectangle, selected, has its actions shown, and its link button is there, hidden.
  const link = page.locator('.excalidraw button[aria-label="Add link"]');
  expect(await link.count()).toBe(1);
  expect(await link.isVisible()).toBe(false);
  // ⌘K, for a link, does nothing, and neither do help and the command palette.
  for (const keys of ["Control+k", "Meta+k", "?", "Control+/", "Control+s"]) {
    await page.keyboard.press(keys);
  }
  expect(await page.locator(".HelpDialog, .command-palette-dialog, .Modal").count()).toBe(0);
  expect(await page.locator(".excalidraw-hyperlinkContainer input").count()).toBe(0);
  // A PNG pasted: uploaded through the host, put on the canvas, and named by the next edit.
  await page.evaluate(async () => {
    const drawing = document.createElement("canvas");
    drawing.width = 8;
    drawing.height = 8;
    const context = drawing.getContext("2d") as CanvasRenderingContext2D;
    context.fillStyle = "#c00";
    context.fillRect(0, 0, 8, 8);
    const png = await new Promise<Blob>((done) => drawing.toBlob((blob) => done(blob as Blob)));
    const pasted = new DataTransfer();
    pasted.items.add(new File([png], "red.png", { type: "image/png" }));
    const target = document.querySelector(".excalidraw") as HTMLElement;
    target.dispatchEvent(
      new ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData: pasted }),
    );
  });
  await expect
    .poll(async () => (await sent(page)).uploads, { timeout: 8000 })
    .toEqual(["image/png"]);
  await expect.poll(async () => (await sent(page)).commits.length, { timeout: 12000 }).toBe(2);
  const pictured = (await sent(page)).commits[1];
  expect(pictured?.baseVersion).toBe(2);
  expect(pictured?.ops.some((op) => /^\/files\/[0-9a-f]{64}$/.test(op.path))).toBe(true);
  expect(pictured?.ops.some((op) => op.op === "add" && op.path.startsWith("/elements/"))).toBe(
    true,
  );
  // An SVG pasted is refused before it is uploaded.
  await page.evaluate(() => {
    const pasted = new DataTransfer();
    pasted.items.add(new File(["<svg/>"], "x.svg", { type: "image/svg+xml" }));
    const target = document.querySelector(".excalidraw") as HTMLElement;
    target.dispatchEvent(
      new ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData: pasted }),
    );
  });
  // A link pasted, which Excalidraw would embed as a page: nothing is embedded, nothing loads.
  await page.evaluate(() => {
    const pasted = new DataTransfer();
    pasted.setData("text/plain", "https://www.youtube.com/watch?v=x");
    const target = document.querySelector(".excalidraw") as HTMLElement;
    target.dispatchEvent(
      new ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData: pasted }),
    );
  });
  await page.waitForTimeout(500);
  expect(await page.locator("iframe, .excalidraw__embeddable").count()).toBe(0);
  expect((await sent(page)).uploads).toEqual(["image/png"]);
  expect(seen.away()).toEqual([]);
  expect(await reported()).toEqual([]);
  await page.context().close();
});

test("the harness would see a blob: image the policy refuses: the canvas's own make none", async () => {
  const { page, reported } = await open(browser, "?diagram");
  await page.evaluate(async () => {
    const image = document.createElement("img");
    image.src = URL.createObjectURL(
      new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" }),
    );
    document.body.append(image);
  });
  await expect.poll(async () => (await reported()).length).toBeGreaterThan(0);
  await page.context().close();
});
