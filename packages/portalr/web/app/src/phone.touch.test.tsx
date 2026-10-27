/**
 * The app on a phone (portalr ADR-0082): the question's Answer within the thumb's reach, one tab
 * stop; what floats as a sheet along the bottom; the composer above the on-screen keyboard.
 */

import { afterEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { open } from "./test/app";
import { AT } from "./test/files";
import { serve as notes, WORLD } from "./test/notes";

/** Files may be attached: a kind offered, so the composer has its Attach. */
const OFFERED = {
  allowed: true,
  limit: 1000,
  kinds: [{ kind: "word_document", extensions: [".docx"], enabled: true, limit: 1000 }],
};
const serve: typeof notes = async (request, path) =>
  path === `${AT}/uploads` ? Response.json(OFFERED) : notes(request, path);

const real = window.visualViewport;
afterEach(() => {
  vi.unstubAllGlobals();
  Object.defineProperty(window, "visualViewport", { value: real, configurable: true });
});

const bottom = (element: Element) => Math.round(element.getBoundingClientRect().bottom);

test("the question's Answer sits above the composer, presses the card's own, and is one tab stop", async () => {
  await page.viewport(390, 844);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
  const bar = document.querySelector("[data-thumb-bar]") as HTMLElement;
  expect(bar).not.toBeNull();
  await expect.poll(() => bar.textContent).toContain("Answer");
  expect(bar.getAttribute("aria-hidden")).toBe("true");
  expect(bar.querySelector("button")?.tabIndex).toBe(-1);
  // One Answer for a reader: the card's.
  expect(screen.getByRole("button", { name: "Answer" }).elements()).toHaveLength(1);
  // Pinned with the composer, within the thumb's reach: at most a quarter of a short window.
  const dock = document.querySelector("[data-composer-dock]") as HTMLElement;
  expect(bottom(dock)).toBeLessThanOrEqual(window.innerHeight);
  expect(dock.getBoundingClientRect().height).toBeLessThanOrEqual(window.innerHeight / 4);
});

test("the account menu, the thread's menu and the attach panel open as sheets", async () => {
  await page.viewport(390, 844);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
  for (const [name, role] of [
    [/^Attach/, "dialog"],
    ["Account: Signed in", "menu"],
    ["Thread actions", "menu"],
  ] as const) {
    const trigger = screen.getByRole("button", { name });
    await expect.element(trigger).toBeVisible();
    await trigger.click();
    const sheet = screen.getByRole(role);
    await expect.element(sheet).toBeVisible();
    await expect.poll(() => bottom(sheet.element())).toBe(window.innerHeight);
    expect(Math.round(sheet.element().getBoundingClientRect().width)).toBe(window.innerWidth);
    await userEvent.keyboard("{Escape}");
    await expect.element(screen.getByRole(role)).not.toBeInTheDocument();
  }
});

test("the composer's dock rises by what the on-screen keyboard covers", async () => {
  await page.viewport(390, 844);
  const viewport = new EventTarget() as EventTarget & { height: number; offsetTop: number };
  viewport.height = window.innerHeight;
  viewport.offsetTop = 0;
  Object.defineProperty(window, "visualViewport", { value: viewport, configurable: true });
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
  const dock = document.querySelector("[data-composer-dock]") as HTMLElement;
  await expect
    .poll(() => document.documentElement.style.getPropertyValue("--keyboard-inset"))
    .toBe("0px");
  viewport.height = window.innerHeight - 300;
  viewport.dispatchEvent(new Event("resize"));
  await expect.poll(() => getComputedStyle(dock).bottom).toBe("300px");
  expect(bottom(dock)).toBeLessThanOrEqual(window.innerHeight - 300);
  await expect.element(screen.getByRole("button", { name: "Send" })).toBeVisible();
});
