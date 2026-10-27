/**
 * Several portal origins in Chromium (portalr ADR-0084): the page reached at `127.0.0.1` and at
 * `localhost`, two origins, frames the sandbox and the editor's shim from each, and both answer;
 * a third origin that frames them is refused by their `frame-ancestors`; and the sandbox's and the
 * shim's `event.origin` checks answer only the portal origin their frame was told, `?host=`, which
 * must be the page's own, so a page at one portal origin can't speak as another.
 */

import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { type Browser, chromium, type Page } from "playwright";
import { afterAll, beforeAll, expect, inject, test } from "vitest";

let browser: Browser;

/** What the third origin's page frames: set by a test, never read from a request. */
let framedByThird = "";

/** A third origin: a page there that frames `framedByThird`. */
const third = createServer((_request, response) => {
  response.writeHead(200, { "Content-Type": "text/html" });
  response.end(`<!doctype html><title>Third</title><iframe src="${framedByThird}"></iframe>`);
});
let thirdOrigin: string;

beforeAll(async () => {
  // `localhost` is 127.0.0.1 here, where the harness listens, whatever the resolver says of ::1.
  browser = await chromium.launch({ args: ["--host-resolver-rules=MAP localhost 127.0.0.1"] });
  await new Promise<void>((listening) => third.listen(0, "127.0.0.1", listening));
  thirdOrigin = `http://127.0.0.1:${(third.address() as AddressInfo).port}`;
});

afterAll(async () => {
  third.close();
  await browser.close();
});

/** Long enough for a frame, its script and a message on a busy CI runner. */
const SETTLED = { timeout: 15_000 };

/** Long enough that a message which was going to arrive has; what is refused never does. */
const SILENCE = 1_500;

/**
 * A page that keeps every message it hears, as `window.heard`, from before its own scripts, and
 * every request made from it, from before it is opened.
 */
async function listening(url: string): Promise<{ page: Page; loaded: string[] }> {
  const page = await browser.newPage();
  const loaded: string[] = [];
  page.on("request", (request) => loaded.push(request.url()));
  await page.addInitScript(() => {
    const heard: unknown[] = [];
    Object.assign(window, { heard });
    addEventListener("message", (event) => heard.push({ origin: event.origin, data: event.data }));
  });
  await page.goto(url);
  return { page, loaded };
}

const heard = (page: Page) =>
  page.evaluate(() => (window as unknown as { heard: unknown[] }).heard);

/** The page frames `src` from its own task, as the app's pages do, and the frame is sent `post`. */
const framing = (page: Page, src: string, post?: { data: unknown; to: string }) =>
  page.evaluate(
    ([src, post]) => {
      const frame = document.createElement("iframe");
      frame.src = src;
      if (post) {
        frame.addEventListener("load", () => frame.contentWindow?.postMessage(post.data, post.to));
      }
      document.body.append(frame);
    },
    [src, post] as const,
  );

/** The sandbox's first word to the portal it was told, once it is listening. */
const PROXY_READY = { jsonrpc: "2.0", method: "ui/notifications/sandbox-proxy-ready" };

/** A mini app, run through `AppFrame` and the bridge at `harness`, in the sandbox at `apps`. */
async function running(harness: string, apps: string): Promise<Page> {
  const page = await browser.newPage();
  const html =
    '<script>parent.postMessage({jsonrpc:"2.0",method:"ui/notifications/size-changed",params:{height:321}},"*")</script>';
  await page.goto(`${harness}?${new URLSearchParams({ app: html, apps })}`);
  return page;
}

const height = (page: Page) =>
  page.getByTitle("Probe: an app made by the agent").evaluate((frame) => frame.style.height);

test("the page at 127.0.0.1 and the page at localhost each run an app in the sandbox beside them", async () => {
  const loopback = await running(inject("harness"), inject("apps"));
  await expect.poll(() => height(loopback), SETTLED).toBe("321px");
  expect(await loopback.evaluate(() => location.hostname)).toBe("127.0.0.1");
  await loopback.close();
  const alias = await running(inject("localhost").harness, inject("localhost").apps);
  await expect.poll(() => height(alias), SETTLED).toBe("321px");
  expect(await alias.evaluate(() => location.hostname)).toBe("localhost");
  await alias.close();
});

test("a third origin that frames the sandbox is refused: it hears nothing from it", async () => {
  framedByThird = `${inject("apps")}/?host=${encodeURIComponent(thirdOrigin)}`;
  const { page } = await listening(`${thirdOrigin}/`);
  await page.waitForTimeout(SILENCE);
  expect(await heard(page)).toEqual([]);
  await page.close();
});

test("the sandbox answers only the portal origin its frame names, which must be the page's own", async () => {
  const { page } = await listening(inject("harness"));
  const own = new URL(inject("harness")).origin;
  // Told this page's origin, the sandbox says it is listening, from the apps' origin.
  await framing(page, `${inject("apps")}/?host=${encodeURIComponent(own)}`);
  await expect
    .poll(() => heard(page), SETTLED)
    .toContainEqual({ origin: inject("apps"), data: JSON.stringify(PROXY_READY) });
  // Told the other portal origin, which also may frame it, it says nothing to this page, and
  // takes nothing from it: its `event.origin` check sees the page's own origin, not that one.
  const other = new URL(inject("localhost").harness).origin;
  const before = (await heard(page)).length;
  await framing(page, `${inject("apps")}/?host=${encodeURIComponent(other)}`, {
    data: {
      jsonrpc: "2.0",
      method: "ui/notifications/sandbox-resource-ready",
      params: { html: "<p>" },
    },
    to: inject("apps"),
  });
  await page.waitForTimeout(SILENCE);
  expect((await heard(page)).length).toBe(before);
  await page.close();
});

/** The editor's shim, told which portal frames it, as `EditorFrame` names it. */
const shim = (editor: string, host: string | null) =>
  `${editor}/.lattice/shim.html${host === null ? "" : `?host=${encodeURIComponent(host)}`}`;

const READY = { type: "lattice:ready", version: "1" };

test("the shim, told two portals, answers the page at each when its frame names that page's origin", async () => {
  for (const [harness, editor] of [
    [inject("harness"), inject("editor")],
    [inject("localhost").harness, inject("editor").replace("127.0.0.1", "localhost")],
  ] as const) {
    const { page } = await listening(harness);
    await framing(page, shim(editor, new URL(harness).origin));
    await expect.poll(() => heard(page), SETTLED).toContainEqual({ origin: editor, data: READY });
    await page.close();
  }
});

test("the shim is inert without a host it was told; with the other portal's, it answers only that one", async () => {
  const { page, loaded } = await listening(inject("harness"));
  const editor = inject("editor");
  // No host, or one the shim wasn't told: nothing runs, and the build isn't even loaded.
  for (const host of [null, "https://evil.example"]) {
    await framing(page, shim(editor, host));
  }
  await page.waitForTimeout(SILENCE);
  expect(await heard(page)).toEqual([]);
  expect(loaded.filter((url) => url.startsWith(`${editor}/`))).toEqual([
    shim(editor, null),
    shim(editor, "https://evil.example"),
  ]);
  // The other portal, which the shim was told: it runs for that one, so the build loads, but it
  // says nothing to this page, and its `event.origin` check takes nothing from it.
  const other = new URL(inject("localhost").harness).origin;
  await framing(page, shim(editor, other), { data: { type: "lattice:open" }, to: editor });
  await page.waitForTimeout(SILENCE);
  expect(await heard(page)).toEqual([]);
  expect(loaded.filter((url) => url === `${editor}/?host=parent`)).toHaveLength(1);
  await page.close();
});

test("a third origin that frames the shim is refused by its frame-ancestors", async () => {
  framedByThird = shim(inject("editor"), thirdOrigin);
  const { page, loaded } = await listening(`${thirdOrigin}/`);
  await page.waitForTimeout(SILENCE);
  expect(await heard(page)).toEqual([]);
  expect(loaded.filter((url) => url.startsWith(`${inject("editor")}/`))).toEqual([framedByThird]);
  await page.close();
});
