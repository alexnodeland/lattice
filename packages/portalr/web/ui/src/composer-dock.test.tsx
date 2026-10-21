import { expect, onTestFinished, test } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Button } from "./button";
import { ComposerDock } from "./composer-dock";

function Thread() {
  return (
    <main className="flex flex-col gap-4 p-4">
      {Array.from({ length: 30 }, (_, at) => (
        <div key={`message-${at + 1}`} className="flex flex-col gap-1">
          <p>Message {at + 1}, a few words long, as a reply is.</p>
          <Button variant="ghost">Copy message {at + 1}</Button>
        </div>
      ))}
      <ComposerDock>
        <textarea aria-label="Message" rows={3} className="w-full" />
      </ComposerDock>
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

test("the page forgets the composer once it goes", async () => {
  const screen = await render(<Thread />);
  await expect
    .poll(() => document.documentElement.style.getPropertyValue("--composer-clearance"))
    .not.toBe("");
  screen.unmount();
  expect(document.documentElement.style.getPropertyValue("--composer-clearance")).toBe("");
});
