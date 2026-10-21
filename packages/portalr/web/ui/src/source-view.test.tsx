import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { JsonView, MOST_ENTRIES } from "./json-view";
import { CONTEXT_LINES, LineDiff, lineCounts, MOST_LINES } from "./line-diff";
import { FOLDED_LINES, SourceView } from "./source-view";
import { axeViolations } from "./test/axe";
import { compare } from "./test/compare";

const numbered = (count: number) =>
  Array.from({ length: count }, (_, at) => `<p>line ${at + 1}</p>`).join("\n");

test("a source: its lines numbered beside it, highlighted, read without its numbers", async () => {
  const screen = await render(
    <SourceView code={'<button id="go">Go</button>\n<p>Done</p>'} language="html" name="HTML" />,
  );
  const region = screen.getByRole("region", { name: "HTML source" });
  await expect.element(region).toBeVisible();
  await expect.element(screen.getByText("· html · 2 lines")).toBeVisible();
  const code = [...region.element().querySelectorAll("code")].map((line) => line.textContent);
  expect(code).toEqual(['<button id="go">Go</button>\n', "<p>Done</p>"]);
  const numbers = [...region.element().querySelectorAll("[aria-hidden=true]")];
  expect(numbers.map((number) => number.textContent)).toEqual(["1", "2"]);
  // Highlighted once the grammar loads: a token's colour is the theme's.
  await expect.poll(() => region.element().querySelector("code span[style]")).not.toBeNull();
  expect(await axeViolations(screen.container)).toEqual([]);
});

test(`beyond ${FOLDED_LINES} lines it is folded, until the reader asks for the rest`, async () => {
  const screen = await render(<SourceView code={numbered(55)} language="html" name="HTML" />);
  const region = screen.getByRole("region", { name: "HTML source" }).element();
  expect(region.querySelectorAll("code")).toHaveLength(FOLDED_LINES);
  const more = screen.getByRole("button", { name: "Show all 55 lines" });
  await expect.element(more).toHaveAttribute("aria-expanded", "false");
  await userEvent.click(more);
  expect(region.querySelectorAll("code")).toHaveLength(55);
  await userEvent.click(
    screen.getByRole("button", { name: `Show the first ${FOLDED_LINES} lines` }),
  );
  expect(region.querySelectorAll("code")).toHaveLength(FOLDED_LINES);
});

test("its long lines wrap on asking, and Copy copies it as written", async () => {
  const screen = await render(<SourceView code="let a = 1;" language="javascript" name="script" />);
  const wrap = screen.getByRole("button", { name: "Wrap the script" });
  await expect.element(wrap).toHaveAttribute("aria-pressed", "false");
  await userEvent.click(wrap);
  await expect.element(wrap).toHaveAttribute("aria-pressed", "true");
  expect(screen.container.querySelector("code")?.className).toContain("whitespace-pre-wrap");
  await expect.element(screen.getByRole("button", { name: "Copy the script" })).toBeVisible();
});

test("a source too long to highlight, or in a language not highlighted, shows as it is", async () => {
  const long = "x".repeat(20_001);
  const screen = await render(<SourceView code={long} language="html" name="HTML" />);
  expect(screen.container.querySelector("code")?.textContent).toBe(long);
  expect(screen.container.querySelector("code span")).toBeNull();
  const plain = await render(<SourceView code="a\nb" language="cobol" name="program" />);
  expect(plain.container.querySelector("code span")).toBeNull();
});

test("lines changed: added and removed marked for a reader, unchanged runs folded", async () => {
  const before = numbered(20);
  const after = before.replace("<p>line 10</p>", "<p>line ten</p>");
  const changed = compare(before, after, "lines");
  expect(lineCounts(changed ?? [])).toEqual({ added: 1, removed: 1 });
  const screen = await render(<LineDiff changes={changed} name="HTML" />);
  const region = screen.getByRole("region", { name: "Changes to the HTML" });
  await expect.element(region.getByRole("insertion")).toHaveTextContent("added: <p>line ten</p>");
  await expect.element(region.getByRole("deletion")).toHaveTextContent("removed: <p>line 10</p>");
  // Lines 1–6 and 14–20 are folded; the change keeps CONTEXT_LINES on each side.
  const unchanged = 20 - 1 - 2 * CONTEXT_LINES;
  await expect
    .element(screen.getByRole("button", { name: "Show 6 unchanged lines" }))
    .toBeVisible();
  await expect
    .element(screen.getByRole("button", { name: "Show 7 unchanged lines" }))
    .toBeVisible();
  expect(6 + 7).toBe(unchanged);
  await userEvent.click(screen.getByRole("button", { name: "Show 6 unchanged lines" }));
  await expect.element(screen.getByText("<p>line 1</p>", { exact: true })).toBeVisible();
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("a lone unchanged line isn't folded, and changes too large to compare say so", async () => {
  const changed = compare("a\nb\nc\nd\n", "a\nb\nc\nd\ne\n", "lines");
  const one = await render(<LineDiff changes={changed} name="text" />);
  await expect.element(one.getByText("a", { exact: true })).toBeVisible();
  expect(one.getByRole("button").elements()).toHaveLength(0);
  const big = await render(<LineDiff changes={null} name="HTML" />);
  await expect.element(big.getByText("Too large to compare.")).toBeVisible();
});

test("JSON as a tree: deep values folded, empty ones as brackets, and Copy as JSON", async () => {
  const data = {
    deep: { deeper: { deepest: true } },
    none: [],
    nothing: {},
    count: 3,
    list: ["a"],
  };
  const screen = await render(<JsonView data={data} name="data" />);
  const tree = screen.getByRole("region", { name: "data" });
  const [deep, deeper] = tree.element().querySelectorAll("[aria-expanded]");
  expect(deep?.getAttribute("aria-expanded")).toBe("true");
  expect(deeper?.getAttribute("aria-expanded")).toBe("false");
  await expect.element(tree.getByText("1 key").first()).toBeVisible();
  await expect.element(tree.getByText("1 item")).toBeVisible();
  await expect.element(tree.getByText("[]")).toBeVisible();
  await expect.element(tree.getByText("{}")).toBeVisible();
  await expect.element(tree.getByText("3", { exact: true })).toBeVisible();
  await expect.element(screen.getByRole("button", { name: "Copy the data" })).toBeVisible();
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("a source's last newline ends its last line, CRLF is a line break, and empty is said", async () => {
  const screen = await render(<SourceView code={"a\r\nb\n"} language="text" name="text" />);
  await expect.element(screen.getByText("· text · 2 lines")).toBeVisible();
  expect([...screen.container.querySelectorAll("code")].map((line) => line.textContent)).toEqual([
    "a\n",
    "b",
  ]);
  const empty = await render(<SourceView code="" language="text" name="note" />);
  await expect.element(empty.getByText("· text · empty")).toBeVisible();
});

test("a change of an empty line alone, and CRLF lines, are compared as lines", async () => {
  const changed = compare("a\r\n\r\nb\r\n", "a\r\nb\r\n", "lines");
  expect(lineCounts(changed ?? [])).toEqual({ added: 0, removed: 1 });
  const screen = await render(<LineDiff changes={changed} name="text" />);
  const removed = screen.getByRole("deletion").element();
  expect(removed.textContent).toBe("removed: ");
});

test("a long change draws MOST_LINES lines, and more on asking", async () => {
  const lines = (prefix: string) =>
    Array.from({ length: MOST_LINES + 5 }, (_, at) => `${prefix}${at}`).join("\n");
  const changed = [
    { kind: "removed" as const, text: `${lines("a")}\n` },
    { kind: "added" as const, text: `${lines("b")}\n` },
  ];
  const screen = await render(<LineDiff changes={changed} name="HTML" />);
  const region = screen.getByRole("region", { name: "Changes to the HTML" }).element();
  expect(region.querySelectorAll("del, ins")).toHaveLength(MOST_LINES);
  await userEvent.click(screen.getByRole("button", { name: /more lines of/ }));
  expect(region.querySelectorAll("del, ins")).toHaveLength(2 * MOST_LINES);
});

test("the lines a fold shows take the focus of its button", async () => {
  const before = numbered(20);
  const changed = compare(before, before.replace("<p>line 10</p>", "<p>ten</p>"), "lines");
  const screen = await render(<LineDiff changes={changed} name="HTML" />);
  await userEvent.click(screen.getByRole("button", { name: "Show 6 unchanged lines" }));
  expect(document.activeElement?.textContent).toBe("<p>line 1</p>");
});

test("a long list shows its first MOST_ENTRIES items, and counts the rest", async () => {
  const screen = await render(
    <JsonView data={{ list: Array.from({ length: MOST_ENTRIES + 3 }, (_, at) => at) }} />,
  );
  await expect.element(screen.getByText("And 3 more, in what Copy copies.")).toBeVisible();
});

test("a long fold of unchanged lines shows MOST_LINES at a time, and the line it reveals is ringed", async () => {
  const before = numbered(MOST_LINES + 50);
  const changed = compare(before, `${before}\n<p>end</p>`, "lines");
  const screen = await render(<LineDiff changes={changed} name="HTML" />);
  const fold = screen.getByRole("button", {
    name: `Show ${MOST_LINES} of ${MOST_LINES + 46} unchanged lines`,
  });
  fold.element().focus();
  await userEvent.keyboard("{Enter}");
  const line = document.activeElement as HTMLElement;
  expect(line.textContent).toBe("<p>line 1</p>");
  expect(getComputedStyle(line).outlineStyle).not.toBe("none");
  await expect
    .element(screen.getByRole("button", { name: "Show 46 unchanged lines" }))
    .toBeVisible();
});
