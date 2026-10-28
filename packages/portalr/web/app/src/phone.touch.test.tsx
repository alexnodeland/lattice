/**
 * The app on a phone (portalr ADR-0082): the request's next step within the thumb's reach, one
 * tab stop, and gone while the card's own button is in view or the keyboard is up; what floats
 * as a sheet along the bottom; the composer above the on-screen keyboard; nothing wider than the
 * page with a sheet open, the keyboard up or a step unfolded, down to a window at 400% zoom.
 */

import { afterEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { open } from "./test/app";
import { AT } from "./test/files";
import { APPROVAL, serve as notes, STEPPED, WORLD } from "./test/notes";
import { wider } from "./test/overflow";

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
  document.documentElement.style.removeProperty("--keyboard-inset");
});

const bottom = (element: Element) => Math.round(element.getBoundingClientRect().bottom);
const bar = () => document.querySelector("[data-thumb-bar]");
const press = () => {
  const button = bar()?.querySelector("button");
  if (button) {
    button.click();
  }
};
const dock = () => document.querySelector("[data-composer-dock]") as HTMLElement;
const noneWider = () => {
  const found = wider();
  expect(found, found.join("\n")).toEqual([]);
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
};
/** A fake visual viewport, `covered` pixels shorter than the window, as a keyboard makes it. */
function keyboard(covered: number) {
  const viewport = new EventTarget() as EventTarget & {
    height: number;
    offsetTop: number;
    scale: number;
  };
  viewport.height = window.innerHeight - covered;
  viewport.offsetTop = 0;
  viewport.scale = 1;
  Object.defineProperty(window, "visualViewport", { value: viewport, configurable: true });
  return viewport;
}

test("the question's Answer sits in the composer's row, presses the card's own, and is one tab stop", async () => {
  await page.viewport(390, 844);
  // A visual viewport of the test's own: the real one's scrolls would measure the keyboard down.
  const viewport = keyboard(0);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
  // The card's Answer is below the fold: the bar shows it.
  await expect.poll(() => bar()?.textContent).toContain("Answer");
  expect(bar()?.getAttribute("aria-hidden")).toBe("true");
  expect(bar()?.querySelector("button")?.tabIndex).toBe(-1);
  // One Answer for a reader: the card's.
  expect(screen.getByRole("button", { name: "Answer" }).elements()).toHaveLength(1);
  expect(bottom(dock())).toBeLessThanOrEqual(window.innerHeight);
  expect(dock().getBoundingClientRect().height).toBeLessThanOrEqual(window.innerHeight / 4);
  // The card's own button scrolled into view: the bar gives way; scrolled away, it is back.
  document.getElementById("request-q1")?.scrollIntoView({ block: "center" });
  await expect.poll(() => bar(), { timeout: 3000 }).toBeNull();
  window.scrollTo(0, 0);
  await expect.poll(() => bar()?.textContent).toContain("Answer");
  // The keyboard up: the bar gives way too.
  viewport.height = window.innerHeight - 300;
  viewport.dispatchEvent(new Event("resize"));
  await expect.poll(() => bar()).toBeNull();
});

test("a stepped question's bar says Next, then Answer, and gives way as it brings the card into view", async () => {
  await page.viewport(390, 844);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, STEPPED);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeInTheDocument();
  const away = async (word: string) => {
    window.scrollTo(0, 0);
    await expect.poll(() => bar()?.textContent).toContain(word);
  };
  await away("Next");
  // Pressed, the bar's Next is the card's: the step is checked (an answer first), the next step
  // comes, and the card is brought into view, where the bar gives way to it.
  await screen.getByRole("radio", { name: /^Yes/ }).click();
  await away("Next");
  press();
  await expect.element(screen.getByText("Formal, or plain?")).toBeInTheDocument();
  await expect.poll(() => bar()).toBeNull();
  await screen.getByRole("radio", { name: /^Yes/ }).click();
  await away("Next");
  press();
  await expect.element(screen.getByText("Review your answers")).toBeInTheDocument();
  await away("Answer");
});

test("a plain approval holds the window's foot, so the bar has nothing to mirror", async () => {
  // A short window: the card's own Approve stays in the thumb's reach, at the window's foot over
  // the thread (portalr ADR-0087), and the bar gives way to it, as it does to any card in view.
  await page.viewport(390, 600);
  const { screen } = await open(
    "/t/acme/w/notes/threads/thr_1",
    serve,
    () => null,
    APPROVAL(undefined),
  );
  const approve = screen.getByRole("button", { name: "Approve" });
  await expect.element(approve).toBeInTheDocument();
  window.scrollTo(0, 0);
  await expect
    .poll(() => {
      const box = approve.element().getBoundingClientRect();
      return box.top >= 0 && box.bottom <= window.innerHeight;
    })
    .toBe(true);
  expect(bar()).toBeNull();
});

for (const [what, review] of [
  ["what it runs", { app: "Blender", runs: "It runs a script." }],
  [
    "what it runs, code and a risk",
    {
      app: "Blender",
      runs: "It runs a script.",
      risk: "network",
      code: "import os\nos.system('curl x')",
    },
  ],
  ["findings", { app: "Blender", runs: "It runs a script.", findings: ["reads a file"] }],
] as const) {
  test(`an approval with ${what} to review first is never mirrored: it is read before it is given`, async () => {
    await page.viewport(390, 844);
    const { screen } = await open(
      "/t/acme/w/notes/threads/thr_1",
      serve,
      () => null,
      APPROVAL(review),
    );
    await expect.element(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    window.scrollTo(0, 0);
    await new Promise((settled) => setTimeout(settled, 300));
    expect(bar()).toBeNull();
  });
}

test("on a small phone the composer's row, bar and all, takes at most a quarter of the window", async () => {
  await page.viewport(375, 667);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
  await expect.poll(() => bar()?.textContent).toContain("Answer");
  expect(dock().getBoundingClientRect().height).toBeLessThanOrEqual(window.innerHeight / 4);
});

test("the account menu, the thread's menu and the attach panel open as sheets, and the page is never wider", async () => {
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
    noneWider();
    await userEvent.keyboard("{Escape}");
    await expect.element(screen.getByRole(role)).not.toBeInTheDocument();
  }
});

test("the attach panel is modal on a phone: a scrim, the focus kept in, and a Done to leave by", async () => {
  await page.viewport(390, 844);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
  await screen.getByRole("button", { name: /^Attach/ }).click();
  const panel = screen.getByRole("dialog");
  await expect.element(panel).toBeVisible();
  expect(panel.element().getAttribute("aria-modal")).toBe("true");
  await expect.element(screen.getByRole("button", { name: "Done" })).toBeVisible();
  await screen.getByRole("button", { name: "Done" }).click();
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
});

test("the composer's dock rises by what the on-screen keyboard covers, and the page is never wider", async () => {
  await page.viewport(390, 844);
  const viewport = keyboard(0);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
  await expect
    .poll(() => document.documentElement.style.getPropertyValue("--keyboard-inset"))
    .toBe("0px");
  const clear = Number.parseFloat(getComputedStyle(dock()).paddingBottom);
  viewport.height = window.innerHeight - 300;
  viewport.dispatchEvent(new Event("resize"));
  await expect.poll(() => getComputedStyle(dock()).bottom).toBe("300px");
  // The home indicator's room goes with the keyboard: the dock keeps only its own padding.
  expect(Number.parseFloat(getComputedStyle(dock()).paddingBottom)).toBeLessThanOrEqual(clear);
  expect(getComputedStyle(dock()).paddingBottom).toBe("16px");
  expect(bottom(dock())).toBeLessThanOrEqual(window.innerHeight - 300);
  await expect.element(screen.getByRole("button", { name: "Send" })).toBeVisible();
  noneWider();
});

for (const width of [320, 390, 768]) {
  test(`a thread at ${width}px with a step unfolded is never wider than the page`, async () => {
    await page.viewport(width, 900);
    const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
    await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
    await screen.getByRole("button", { name: "2 steps" }).click();
    const step = screen.getByRole("button", { name: /list_artifacts/ }).first();
    await expect.element(step).toBeVisible();
    await step.click();
    await expect.element(screen.getByText("Arguments").first()).toBeVisible();
    noneWider();
  });
}

test("a window at 400% zoom (320×256) scrolls down, never sideways, with the dock in the flow", async () => {
  await page.viewport(320, 256);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeInTheDocument();
  noneWider();
  expect(getComputedStyle(dock()).position).toBe("static");
  // The bar gives way in a short window: nothing pinned covers most of the page.
  const shown = bar();
  expect(shown === null || getComputedStyle(shown).display === "none").toBe(true);
});
