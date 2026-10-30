/**
 * ui's Markdown under the policy both UIs share, in Chromium: every element, streamed or whole,
 * each hostile message, and each control, with not one violation of the policy, and not one use of
 * WebAssembly, which the harness reports and the policy refuses (portalr ADR-0041, as amended),
 * since Markdown and its add-ons need none (ADR-0044). The page is built as the UIs are, so what is
 * checked is what ships (ADR-0043), and draws each from its own task, where a string it evaluated
 * would be refused (ADR-0047).
 */

import type { Browser, Page } from "playwright";
import { afterAll, beforeAll, expect, test } from "vitest";
import { GALLERY, HOSTILE } from "../src/test/markdown";
import { connected, open } from "./harness";

let browser: Browser;

beforeAll(async () => {
  browser = await connected();
});

afterAll(() => browser.close());

/** How long a page may go without drawing more before it is said to be stuck, in milliseconds. */
const STALLED = 30_000;

/** How the page's drawing ended, "whole" or its error, waiting while it makes progress. */
async function drawn(page: Page): Promise<string> {
  let seen = "";
  for (;;) {
    const handle = await page.waitForFunction(
      (before) => {
        const root = document.documentElement.dataset;
        const streamed = root.streamed ?? "";
        return root.drawn ?? root.error ?? (streamed !== before ? `+${streamed}` : null);
      },
      seen,
      { timeout: STALLED },
    );
    const now = String(await handle.jsonValue());
    if (!now.startsWith("+")) {
      return now;
    }
    seen = now.slice(1);
  }
}

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
  // Drawn whole, or stopped by an error, which the page says on its root. A stream takes a slow
  // runner a while, a minute and more under load: it is waited on while it makes progress, and
  // fails only once it has made none for `STALLED` milliseconds.
  const ended = await drawn(harness.page).catch((error: unknown) => `not drawn: ${String(error)}`);
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
  const seen = await reported(2);
  expect(seen.some((line) => line.startsWith("style-src-attr:"))).toBe(true);
  expect(seen.some((line) => line.startsWith("style-src-elem:"))).toBe(true);
  await page.context().close();
});

test("the harness sees WebAssembly: a module is refused under the policy, and the call is reported", async () => {
  const { page, reported } = await open(browser);
  // The smallest module: its magic, `\0asm`, and version 1. The policy has no
  // 'wasm-unsafe-eval' (portalr ADR-0041, amended by artifactr ADR-0088), so compiling it fails.
  const refused = await page.evaluate(async () => {
    try {
      await WebAssembly.compile(new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0]));
      return null;
    } catch (error) {
      return error instanceof Error ? error.name : String(error);
    }
  });
  expect(refused).toBe("CompileError");
  // The call, as the harness wraps it, and the policy's own report of the refusal.
  expect(await reported(2)).toEqual(["WebAssembly.compile", "script-src: wasm-eval at "]);
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
