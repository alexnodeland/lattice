/**
 * ui's Markdown under portalr's Content-Security-Policy, in Chromium: every element, streamed or
 * whole, each hostile message, and each control, with not one violation of the policy. The page
 * is built as the UIs are, so what is checked is what ships (portalr ADR-0043).
 */

import { type Browser, chromium, type Page } from "playwright";
import { afterAll, beforeAll, expect, inject, test } from "vitest";
import { GALLERY, HOSTILE } from "../src/test/markdown";

let browser: Browser;

beforeAll(async () => {
  browser = await chromium.launch();
});

afterAll(() => browser.close());

/** A page on the harness, and what it has reported: each violation of the policy, and each error. */
async function opened(): Promise<{ page: Page; reported: () => Promise<string[]> }> {
  // The clipboard is the page's to write, so Copy copies, as it does for a person.
  const context = await browser.newContext({ permissions: ["clipboard-read", "clipboard-write"] });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(`error: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(`console: ${message.text()}`);
    }
  });
  // Before the page's own scripts, and whatever its policy: Playwright adds it, not the page.
  await page.addInitScript(() => {
    const seen: string[] = [];
    Object.assign(window, { violations: seen });
    document.addEventListener("securitypolicyviolation", (event) => {
      seen.push(`${event.effectiveDirective}: ${event.blockedURI} at ${event.sourceFile}`);
    });
  });
  await page.goto(inject("harness"));
  await page.waitForFunction(() => typeof window.show === "function");
  const reported = async () => {
    // A violation is reported as a task of its own, after what caused it.
    await page.evaluate(() => new Promise((settled) => setTimeout(settled, 50)));
    const violations = await page.evaluate(
      () => (window as unknown as { violations: string[] }).violations,
    );
    return [...violations, ...errors];
  };
  return { page, reported };
}

test("the harness sees a violation: an inline style, and a style element, each refused", async () => {
  const { page, reported } = await opened();
  await page.evaluate(() => {
    document.body.insertAdjacentHTML("beforeend", '<p style="color: red">styled</p>');
    const sheet = document.createElement("style");
    sheet.textContent = "p { color: red }";
    document.head.append(sheet);
  });
  const seen = await reported();
  expect(seen.some((line) => line.startsWith("style-src-attr:"))).toBe(true);
  expect(seen.some((line) => line.startsWith("style-src-elem:"))).toBe(true);
  await page.context().close();
});

test("every element renders under the policy", async () => {
  const { page, reported } = await opened();
  await page.evaluate((text) => window.show(text), GALLERY);
  await expect(page.getByRole("heading", { name: "The launch plan" }).isVisible()).resolves.toBe(
    true,
  );
  expect(await page.getByRole("note").count()).toBe(5);
  expect(await reported()).toEqual([]);
  await page.context().close();
});

test("every element, streamed a character at a time, renders under the policy", async () => {
  const { page, reported } = await opened();
  await page.evaluate((text) => window.stream(text), GALLERY);
  expect(await page.getByRole("note").count()).toBe(5);
  expect(await reported()).toEqual([]);
  await page.context().close();
});

test("a block's controls work under the policy: Wrap, and Copy", async () => {
  const { page, reported } = await opened();
  await page.evaluate((text) => window.show(text), GALLERY);
  await page.getByRole("button", { name: "Wrap the ts code" }).click();
  await page.getByRole("button", { name: "Copy the ts code" }).click();
  await expect(
    page.getByRole("button", { name: "Wrap the ts code" }).getAttribute("aria-pressed"),
  ).resolves.toBe("true");
  await page.getByRole("button", { name: "Copied the ts code" }).waitFor();
  await expect(page.evaluate(() => navigator.clipboard.readText())).resolves.toContain(
    "export function greet",
  );
  expect(await reported()).toEqual([]);
  await page.context().close();
});

test("a diagram, with diagrams off or on, shows as its source under the policy", async () => {
  const { page, reported } = await opened();
  const fence = "```mermaid\nflowchart LR\n  A --> B\n```";
  for (const mermaid of [false, true]) {
    await page.evaluate(
      ([text, on]) => window.show(text, { addons: { math: true, mermaid: on } }),
      [fence, mermaid] as const,
    );
    expect(await page.getByRole("region", { name: "mermaid code" }).count()).toBe(1);
  }
  expect(await reported()).toEqual([]);
  await page.context().close();
});

test("math, drawn and off, and highlighted code, render under the policy", async () => {
  const { page, reported } = await opened();
  await page.evaluate((text) => window.show(text), GALLERY);
  await page.locator("math").first().waitFor();
  await page.locator('[aria-label="python code"] span').first().waitFor();
  expect(await page.locator("math").count()).toBe(2);
  await page.evaluate(
    (text) => window.show(text, { addons: { math: false, mermaid: false } }),
    GALLERY,
  );
  await page.getByText("Math is off here: this is the formula's source.").waitFor();
  expect(await reported()).toEqual([]);
  await page.context().close();
});

test.each(HOSTILE)(
  "hostile Markdown, whole and streamed, breaks nothing of the policy: %s",
  async (text) => {
    const { page, reported } = await opened();
    await page.evaluate((hostile) => window.show(hostile), text);
    await page.evaluate((hostile) => window.stream(hostile), text);
    expect(await page.locator("#root script, #root iframe, #root img").count()).toBe(0);
    expect(await reported()).toEqual([]);
    await page.context().close();
  },
);
