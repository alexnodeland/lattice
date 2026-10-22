import { expect, onTestFinished, test } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Button } from "./button";
import { ComposerDock } from "./composer-dock";

function Thread({ rows = 3, after = true }: { rows?: number; after?: boolean }) {
  return (
    <main id="main" tabIndex={-1} className="flex flex-col gap-4 p-4">
      {Array.from({ length: 30 }, (_, at) => (
        <div key={`message-${at + 1}`} className="flex flex-col gap-1">
          <p>Message {at + 1}, a few words long, as a reply is.</p>
          <Button variant="ghost">Copy message {at + 1}</Button>
        </div>
      ))}
      <ComposerDock>
        <textarea aria-label="Message" rows={rows} className="w-full" />
      </ComposerDock>
      {/* What follows the composer in a thread, such as its files. */}
      {after && <p className="h-24">Add files to this thread</p>}
    </main>
  );
}

for (const [width, height] of [
  [1280, 800],
  [390, 844],
] as const) {
  test(`what the keyboard reaches stops above the composer, ${width} wide`, async () => {
    await page.viewport(width, height);
    onTestFinished(() => page.viewport(414, 896));
    window.scrollTo(0, 0);
    const screen = await render(<Thread />);
    const dock = screen.getByRole("textbox", { name: "Message" }).element()
      .parentElement as HTMLElement;
    // The page says how tall the composer is, and keeps that much clear as it scrolls to a control.
    await expect
      .poll(() => document.documentElement.style.getPropertyValue("--composer-clearance"))
      .toBe(`${dock.getBoundingClientRect().height}px`);
    for (let at = 1; at <= 30; at += 1) {
      await userEvent.tab();
      const focused = document.activeElement as HTMLElement;
      const bottom = focused.getBoundingClientRect().bottom;
      expect(bottom, `${focused.textContent} is under the composer`).toBeLessThanOrEqual(
        dock.getBoundingClientRect().top + 1,
      );
    }
  });
}

for (const [width, height] of [
  [1280, 800],
  [390, 844],
] as const) {
  // Pins a guarantee main already met before the dock: at the end, the composer is back in its
  // own place in the flow, below the last message.
  test(`at the end of the page, the last message is wholly above the composer (pinned), ${width} wide`, async () => {
    await page.viewport(width, height);
    onTestFinished(() => page.viewport(414, 896));
    const screen = await render(<Thread />);
    window.scrollTo(0, document.documentElement.scrollHeight);
    await new Promise((frame) => requestAnimationFrame(frame));
    const dock = screen.getByRole("textbox", { name: "Message" }).element()
      .parentElement as HTMLElement;
    const last = screen.getByRole("button", { name: "Copy message 30" }).element();
    expect(last.getBoundingClientRect().bottom).toBeLessThanOrEqual(
      dock.getBoundingClientRect().top,
    );
  });
}

test("going back with Shift+Tab stops above the composer too", async () => {
  await page.viewport(390, 844);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(<Thread />);
  const dock = screen.getByRole("textbox", { name: "Message" }).element()
    .parentElement as HTMLElement;
  (screen.getByRole("textbox", { name: "Message" }).element() as HTMLElement).focus();
  for (let at = 30; at >= 25; at -= 1) {
    await userEvent.keyboard("{Shift>}{Tab}{/Shift}");
    const focused = document.activeElement as HTMLElement;
    expect(focused.textContent).toBe(`Copy message ${at}`);
    expect(focused.getBoundingClientRect().bottom).toBeLessThanOrEqual(
      dock.getBoundingClientRect().top + 1,
    );
  }
});

/**
 * An anchor scrolls its target to the top of the window, which the padding at the foot doesn't
 * move: a skip link to `#main` still lands at the top. The padding is what keeps a target near the
 * end clear of the composer: one scrolled to by `scrollIntoView` at the window's foot.
 */
test("a skip link lands at the top; a target near the end stops above the composer", async () => {
  onTestFinished(() => history.replaceState(null, "", location.pathname + location.search));
  const screen = await render(<Thread />);
  window.scrollTo(0, document.documentElement.scrollHeight);
  location.hash = "";
  location.hash = "#main";
  await new Promise((frame) => requestAnimationFrame(frame));
  const main = screen.container.querySelector("#main") as HTMLElement;
  expect(Math.round(main.getBoundingClientRect().top)).toBe(0);
  window.scrollTo(0, 0);
  const dock = screen.getByRole("textbox", { name: "Message" }).element()
    .parentElement as HTMLElement;
  const target = screen.getByRole("button", { name: "Copy message 20" }).element();
  target.scrollIntoView({ block: "end" });
  await new Promise((frame) => requestAnimationFrame(frame));
  expect(target.getBoundingClientRect().bottom).toBeLessThanOrEqual(
    dock.getBoundingClientRect().top + 1,
  );
});

test("focusing the composer from partway down doesn't move the page", async () => {
  const screen = await render(<Thread />);
  window.scrollTo(0, 400);
  await new Promise((frame) => requestAnimationFrame(frame));
  const before = window.scrollY;
  (screen.getByRole("textbox", { name: "Message" }).element() as HTMLElement).focus();
  await new Promise((frame) => requestAnimationFrame(frame));
  expect(window.scrollY).toBe(before);
});

test("a composer that grows, by lines or a row of files, says its new height", async () => {
  const screen = await render(<Thread rows={2} />);
  const area = screen.getByRole("textbox", { name: "Message" }).element() as HTMLTextAreaElement;
  const clearance = () => document.documentElement.style.getPropertyValue("--composer-clearance");
  await expect.poll(clearance).not.toBe("");
  const before = Number.parseFloat(clearance());
  area.rows = 8;
  await expect.poll(() => Number.parseFloat(clearance())).toBeGreaterThan(before);
  const files = document.createElement("p");
  files.textContent = "notes.docx, 12 kB";
  area.parentElement?.append(files);
  const grown = Number.parseFloat(clearance());
  await expect.poll(() => Number.parseFloat(clearance())).toBeGreaterThan(grown);
  files.remove();
});

test("the page forgets the composer once it goes", async () => {
  const screen = await render(<Thread />);
  await expect
    .poll(() => document.documentElement.style.getPropertyValue("--composer-clearance"))
    .not.toBe("");
  screen.unmount();
  expect(document.documentElement.style.getPropertyValue("--composer-clearance")).toBe("");
});
