import { expect, onTestFinished, test } from "vitest";
import { commands } from "vitest/browser";
import { render } from "vitest-browser-react";
import { StatusBadge, type Tone } from "./status-badge";
import { contrast, token } from "./test/colours";

const TONES: readonly Tone[] = [
  "working",
  "waiting",
  "done",
  "failed",
  "retrying",
  "queued",
  "stopped",
  "near",
  "over",
];

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

test("every tone is a mark and a word with no box, and only waiting for you takes the working colour", async () => {
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
    // No box of its own: the word reads on whatever it sits on, the paper here.
    expect(style.backgroundColor).toBe("rgba(0, 0, 0, 0)");
    expect(style.borderTopWidth).toBe("0px");
    expect(contrast(style.color, token("paper"))).toBeGreaterThanOrEqual(4.5);
    expect(style.color === token("accent")).toBe(tone === "waiting");
  }
});

test("working stops turning when motion is reduced", async () => {
  onTestFinished(() => commands.reduceMotion(true));
  await commands.reduceMotion(false);
  const screen = await render(<StatusBadge tone="working">Working</StatusBadge>);
  const glyph = screen.getByText("Working").element().firstElementChild as Element;
  expect(getComputedStyle(glyph).animationName).toBe("spin");
  await commands.reduceMotion(true);
  expect(getComputedStyle(glyph).animationName).toBe("none");
});

test("still, working keeps a shape of its own, apart from queued's", async () => {
  const screen = await render(
    <div>
      <StatusBadge tone="working">Working</StatusBadge>
      <StatusBadge tone="queued">Queued</StatusBadge>
    </div>,
  );
  const shape = (word: string) => {
    const style = getComputedStyle(screen.getByText(word).element().firstElementChild as Element);
    return [style.borderTopStyle, style.borderRightColor === style.borderTopColor].join();
  };
  expect(shape("Working")).not.toBe(shape("Queued"));
});

test("a budget nearly spent and one overspent have shapes of their own", async () => {
  const screen = await render(
    <div>
      <StatusBadge tone="near">Near budget</StatusBadge>
      <StatusBadge tone="over">Over budget</StatusBadge>
    </div>,
  );
  const near = getComputedStyle(
    screen.getByText("Near budget").element().firstElementChild as Element,
  );
  const over = getComputedStyle(
    screen.getByText("Over budget").element().firstElementChild as Element,
  );
  expect(near.backgroundImage).toContain("linear-gradient");
  expect(over.clipPath).toContain("polygon");
});

test("a budget's states are marks of the gold and the red, and their words stay in the ink", async () => {
  const screen = await render(
    <div>
      <StatusBadge tone="near">Near budget</StatusBadge>
      <StatusBadge tone="over">Over budget</StatusBadge>
    </div>,
  );
  const near = getComputedStyle(screen.getByText("Near budget").element());
  const over = getComputedStyle(screen.getByText("Over budget").element());
  const mark = (word: string) =>
    getComputedStyle(screen.getByText(word).element().firstElementChild as Element);
  // The mark carries the colour (portalr ADR-0080); the word has no box (ADR-0081).
  expect(near.backgroundColor).toBe("rgba(0, 0, 0, 0)");
  expect(over.backgroundColor).toBe("rgba(0, 0, 0, 0)");
  expect(mark("Near budget").borderTopColor).toBe(token("status-warn"));
  expect(mark("Over budget").backgroundColor).toBe(token("status-failed"));
  expect(near.color).toBe(token("fg"));
  expect(over.color).toBe(token("fg"));
});

test("failed is marked in the red, retrying in the gold, with no box, and succeeded is neutral", async () => {
  const screen = await render(
    <div>
      <StatusBadge tone="failed">Dead-lettered</StatusBadge>
      <StatusBadge tone="retrying">Retrying</StatusBadge>
      <StatusBadge tone="done">Succeeded</StatusBadge>
    </div>,
  );
  const badge = (word: string) => getComputedStyle(screen.getByText(word).element());
  const glyph = (word: string) =>
    getComputedStyle(screen.getByText(word).element().firstElementChild as Element);
  expect(badge("Dead-lettered").backgroundColor).toBe("rgba(0, 0, 0, 0)");
  expect(glyph("Dead-lettered").backgroundColor).toBe(token("status-failed"));
  expect(badge("Retrying").backgroundColor).toBe("rgba(0, 0, 0, 0)");
  expect(glyph("Retrying").borderTopColor).toBe(token("status-warn"));
  expect(badge("Succeeded").backgroundColor).toBe("rgba(0, 0, 0, 0)");
  expect(badge("Succeeded").color).toBe(token("muted"));
});

test("retrying's shape is apart from queued's and from waiting's, so colour is never what tells them", async () => {
  const screen = await render(
    <div>
      <StatusBadge tone="retrying">Retrying</StatusBadge>
      <StatusBadge tone="queued">Queued</StatusBadge>
      <StatusBadge tone="waiting">Waiting for you</StatusBadge>
    </div>,
  );
  const shape = (word: string) => {
    const style = getComputedStyle(screen.getByText(word).element().firstElementChild as Element);
    return [
      style.borderTopStyle,
      style.borderRadius,
      style.transform,
      style.backgroundColor === "rgba(0, 0, 0, 0)",
    ].join("|");
  };
  const shapes = new Set([shape("Retrying"), shape("Queued"), shape("Waiting for you")]);
  expect(shapes.size).toBe(3);
});

test("under forced colours a shape keeps its own colour, which the border alone would not tell", async () => {
  onTestFinished(() => commands.forcedColors(false));
  const screen = await render(
    <div>
      <StatusBadge tone="failed">Dead-lettered</StatusBadge>
      <StatusBadge tone="over">Over budget</StatusBadge>
    </div>,
  );
  // Read before the colours are forced: a probe's own colour is forced then too.
  const red = token("status-failed");
  await commands.forcedColors(true);
  for (const word of ["Dead-lettered", "Over budget"]) {
    const glyph = screen.getByText(word).element().firstElementChild as Element;
    expect(getComputedStyle(glyph).forcedColorAdjust, word).toBe("none");
    expect(getComputedStyle(glyph).backgroundColor, word).toBe(red);
  }
});
