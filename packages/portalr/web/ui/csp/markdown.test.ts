/**
 * ui's Markdown under the policy both UIs share, in Chromium: every element, streamed or whole,
 * each hostile message, and each control, with not one violation of the policy, and not one use of
 * WebAssembly, which the harness reports (portalr ADR-0041), since Markdown and its add-ons need
 * none (ADR-0044). The page is built as the UIs are, so what is checked is what ships (ADR-0043),
 * and draws each from its own task, where a string it evaluated would be refused (ADR-0047).
 */

import { type Browser, chromium } from "playwright";
import { afterAll, beforeAll, expect, test } from "vitest";
import { GALLERY, HOSTILE } from "../src/test/markdown";
import { open } from "./harness";

let browser: Browser;

beforeAll(async () => {
  browser = await chromium.launch();
});

afterAll(() => browser.close());

/** The harness's page, drawing `text` from its own task, streamed or whole, as `options` say. */
async function shown(
  text: string,
  { stream = false, on = [], off = [] }: { stream?: boolean; on?: string[]; off?: string[] } = {},
) {
  const search = new URLSearchParams({ markdown: text });
  if (stream) {
    search.set("stream", "");
  }
  if (on.length > 0) {
    search.set("on", on.join(","));
  }
  if (off.length > 0) {
    search.set("off", off.join(","));
  }
  const harness = await open(browser, `?${search}`);
  // Drawn whole, or stopped by an error, which the page says on its root; a stream takes a slow
  // runner a while. Either way that it didn't finish says why, with what the page reported.
  const ended = await harness.page
    .waitForFunction(
      () => document.documentElement.dataset.drawn ?? document.documentElement.dataset.error,
      null,
      { timeout: 50_000 },
    )
    .then((handle) => handle.jsonValue())
    .catch((error: unknown) => `not drawn: ${String(error)}`);
  if (ended !== "whole") {
    throw new Error(`${ended}\n${(await harness.reported()).join("\n")}`);
  }
  return harness;
}

test("the harness sees a violation: an inline style, and a style element, each refused", async () => {
  const { page, reported } = await open(browser);
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
  const { page, reported } = await open(browser);
  // The smallest module: its magic, `\0asm`, and version 1.
  const compiled = await page.evaluate(async () => {
    const module = await WebAssembly.compile(new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0]));
    return module instanceof WebAssembly.Module;
  });
  expect(compiled).toBe(true);
  expect(await reported()).toEqual(["WebAssembly.compile"]);
  await page.context().close();
});

test("every element renders under the policy", async () => {
  const { page, reported } = await shown(GALLERY);
  await page.getByRole("heading", { name: "The launch plan" }).waitFor();
  expect(await page.getByRole("note").count()).toBe(5);
  expect(await reported()).toEqual([]);
  await page.context().close();
});

test("every element, streamed a character at a time, renders under the policy", async () => {
  const { page, reported } = await shown(GALLERY, { stream: true });
  await page.getByRole("heading", { name: "The launch plan" }).waitFor();
  expect(await page.getByRole("note").count()).toBe(5);
  expect(await reported()).toEqual([]);
  await page.context().close();
});

test("a block's controls work under the policy: Wrap, and Copy", async () => {
  const { page, reported } = await shown(GALLERY);
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
  const fence = "```mermaid\nflowchart LR\n  A --> B\n```";
  for (const on of [[], ["markdown:mermaid"]]) {
    const { page, reported } = await shown(fence, { on });
    await page.getByRole("region", { name: "mermaid code" }).waitFor();
    expect(await page.getByRole("region", { name: "mermaid code" }).count()).toBe(1);
    expect(await reported()).toEqual([]);
    await page.context().close();
  }
});

test("math, drawn and off, and highlighted code, render under the policy", async () => {
  const drawn = await shown(GALLERY);
  await drawn.page.locator("math").first().waitFor();
  await drawn.page.locator('[aria-label="python code"] span').first().waitFor();
  expect(await drawn.page.locator("math").count()).toBe(2);
  expect(await drawn.reported()).toEqual([]);
  await drawn.page.context().close();
  const off = await shown(GALLERY, { off: ["markdown:math"] });
  await off.page.getByText("Math is off here: this is the formula's source.").first().waitFor();
  expect(await off.reported()).toEqual([]);
  await off.page.context().close();
});

test.each(HOSTILE)(
  "hostile Markdown, whole and streamed, breaks nothing of the policy: %s",
  async (text) => {
    for (const stream of [false, true]) {
      const { page, reported } = await shown(text, { stream });
      await page.locator("#root > *").first().waitFor({ state: "attached" });
      expect(await page.locator("#root script, #root iframe, #root img").count()).toBe(0);
      expect(await reported()).toEqual([]);
      await page.context().close();
    }
  },
);
