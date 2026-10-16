import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { AnsiText, runs } from "./ansi";

const ESC = "\u001b";

const text = (line: string) =>
  runs(line)
    .map((each) => each.text)
    .join("");

test("the eight colours and bold are taken, and reset ends them", () => {
  expect(
    runs(`plain ${ESC}[31mred${ESC}[0m ${ESC}[1;32mbold green${ESC}[22m green${ESC}[39m!`),
  ).toEqual([
    { start: 0, text: "plain ", colour: null, bold: false },
    { start: 6, text: "red", colour: 1, bold: false },
    { start: 9, text: " ", colour: null, bold: false },
    { start: 10, text: "bold green", colour: 2, bold: true },
    { start: 20, text: " green", colour: 2, bold: false },
    { start: 26, text: "!", colour: null, bold: false },
  ]);
  // A bright colour is the same colour; no code at all is a reset.
  expect(runs(`${ESC}[94mb${ESC}[m x`)).toEqual([
    { start: 0, text: "b", colour: 4, bold: false },
    { start: 1, text: " x", colour: null, bold: false },
  ]);
});

test("every other escape is stripped: movement, clearing, titles, links, backgrounds, richer colours", () => {
  const hostile = [
    `a${ESC}[2Jb`, // clear the screen
    `a${ESC}[10;20Hb`, // move the cursor
    `a${ESC}[?25lb`, // hide it
    `a${ESC}]0;a title\u0007b`, // a window title
    `a${ESC}]8;;https://evil.test\u0007b${ESC}]8;;\u0007`, // a link
    `a${ESC}]52;c;ZXZpbA==\u0007b`, // the clipboard
    `a${ESC}[41mb${ESC}[0m`, // a background
    `a${ESC}[38;5;196mb`, // a 256-colour
    `a${ESC}[38;2;255;0;0mb`, // a true colour
    `a${ESC}Pq#0;2;0;0;0${ESC}\\b`, // a device control string
    `a${ESC}cb`, // a reset of the terminal
    `a\rb`, // a carriage return, which would overwrite
    `a\u0008b`, // a backspace
    `a\u0007b`, // a bell
    `a${ESC}`, // an escape with nothing
    `a${ESC}[`, // a sequence that never ends
  ];
  expect(hostile.map((line) => text(line))).toEqual([
    "ab",
    "ab",
    "ab",
    "ab",
    "ab",
    "ab",
    "ab",
    "ab",
    "ab",
    "ab",
    "ab",
    "ab",
    "ab",
    "ab",
    "a",
    "a",
  ]);
  // None of them coloured what follows, but for the colours the palette has.
  expect(runs(`a${ESC}[41mb`).every((each) => each.colour === null)).toBe(true);
  expect(runs(`${ESC}[38;5;196mb`)).toEqual([{ start: 0, text: "b", colour: null, bold: false }]);
});

test("a tab and a newline stay, and a hostile line is read at once", () => {
  expect(text("a\tb\nc")).toBe("a\tb\nc");
  const started = performance.now();
  const hostile = `${ESC}[${"1;".repeat(100_000)}m${ESC}]${"x".repeat(100_000)}${ESC}[`.repeat(20);
  expect(text(hostile).length).toBeLessThan(hostile.length);
  expect(performance.now() - started).toBeLessThan(1000);
});

test("a line is text in spans of the palette's colours, and never markup", async () => {
  const screen = await render(
    <p data-testid="line">
      <AnsiText line={`${ESC}[31m<b>red</b>${ESC}[0m & <script>x</script>`} />
    </p>,
  );
  const line = screen.getByTestId("line").element();
  expect(line.textContent).toBe("<b>red</b> & <script>x</script>");
  expect(line.querySelector("b, script")).toBeNull();
  const red = line.querySelector("span");
  expect(red?.style.color).toBe("var(--ansi-1)");
});
