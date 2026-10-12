import { expect, onTestFinished, test } from "vitest";
import { commands } from "vitest/browser";
import { render } from "vitest-browser-react";
import { StatusBadge, type Tone } from "./status-badge";
import { contrast, token } from "./test/colours";

const TONES: readonly Tone[] = ["working", "waiting", "done", "failed", "queued", "stopped"];

test("a status says its word, with a shape hidden beside it", async () => {
  const screen = await render(<StatusBadge tone="failed">Dead-lettered</StatusBadge>);
  const badge = screen.getByText("Dead-lettered").element();
  expect(badge.textContent).toBe("Dead-lettered");
  expect(badge.firstElementChild?.getAttribute("aria-hidden")).toBe("true");
});

test("a live status is announced as one", async () => {
  const screen = await render(
    <StatusBadge tone="working" live>
      Working
    </StatusBadge>,
  );
  await expect.element(screen.getByRole("status")).toHaveTextContent("Working");
});

test("every tone's word reads on its pill, and only waiting for you takes the working colour", async () => {
  const screen = await render(
    <div>
      {TONES.map((tone) => (
        <StatusBadge key={tone} tone={tone}>
          {tone}
        </StatusBadge>
      ))}
    </div>,
  );
  for (const tone of TONES) {
    const style = getComputedStyle(screen.getByText(tone).element());
    expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
    expect(style.backgroundColor === token("accent")).toBe(tone === "waiting");
  }
});

test("working stops turning when motion is reduced", async () => {
  onTestFinished(() => commands.reduceMotion(false));
  const screen = await render(<StatusBadge tone="working">Working</StatusBadge>);
  const glyph = screen.getByText("Working").element().firstElementChild as Element;
  expect(getComputedStyle(glyph).animationName).toBe("spin");
  await commands.reduceMotion(true);
  expect(getComputedStyle(glyph).animationName).toBe("none");
});
