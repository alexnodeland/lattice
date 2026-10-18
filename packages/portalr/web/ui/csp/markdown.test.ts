/**
 * ui's Markdown under the policy both UIs share, in Chromium: every element, streamed or whole,
 * each hostile message, and each control, with not one violation of the policy, and not one use of
 * WebAssembly. The policy allows first-party WebAssembly (portalr ADR-0041), so it can't refuse a
 * module here; the page reports each reach for one instead, since Markdown and its add-ons need
 * none (ADR-0044). The page is built as the UIs are, so what is checked is what ships (ADR-0043).
 */

import { type Browser, chromium, type Page } from "playwright";
import { afterAll, beforeAll, expect, inject, test } from "vitest";
import { GALLERY, HOSTILE } from "../src/test/markdown";

let browser: Browser;

beforeAll(async () => {
  browser = await chromium.launch();
});

afterAll(() => browser.close());

/** What compiles or instantiates WebAssembly: a page that reaches for one of these uses it. */
const COMPILING = ["compile", "compileStreaming", "instantiate", "instantiateStreaming", "Module"];

/**
 * A page on the harness, and what it has reported: each violation of the policy, each use of
 * WebAssembly, and each error.
 */
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
  await page.addInitScript((compiling) => {
    const seen: string[] = [];
    Object.assign(window, { violations: seen });
    document.addEventListener("securitypolicyviolation", (event) => {
      seen.push(`${event.effectiveDirective}: ${event.blockedURI} at ${event.sourceFile}`);
    });
    const wasm = new Proxy(WebAssembly, {
      get(target, key) {
        if (typeof key === "string" && compiling.includes(key)) {
          seen.push(`WebAssembly.${key}`);
        }
        return Reflect.get(target, key);
      },
    });
    Object.defineProperty(window, "WebAssembly", { value: wasm });
  }, COMPILING);
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

test("the harness sees WebAssembly: a module compiles under the policy, and is reported", async () => {
  const { page, reported } = await opened();
  // The smallest module: its magic, `\0asm`, and version 1.
  const compiled = await page.evaluate(async () => {
    const module = await WebAssembly.compile(new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0]));
    return module instanceof WebAssembly.Module;
  });
  expect(compiled).toBe(true);
  expect(await reported()).toEqual(["WebAssembly.compile", "WebAssembly.Module"]);
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
