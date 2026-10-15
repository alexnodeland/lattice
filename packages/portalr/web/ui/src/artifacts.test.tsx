import type { Change } from "@portalr/client";
import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import {
  ArtifactContent,
  Diff,
  json,
  LONGEST_TITLE,
  markdown,
  plainTitle,
  rendererFor,
} from "./artifacts";
import { contrast, token } from "./test/colours";

const renderers = new Map([["note", markdown()]]);

test("a kind with a renderer renders through it: a note's Markdown", async () => {
  const screen = await render(
    <ArtifactContent kind="note" data={{ text: "# Launch\n\n**Monday**" }} renderers={renderers} />,
  );
  await expect.element(screen.getByRole("heading", { name: "Launch" })).toBeVisible();
  await expect.element(screen.getByText("Monday")).toBeVisible();
});

test("a kind without one shows its data as JSON, so it is never invisible", async () => {
  const screen = await render(
    <ArtifactContent kind="plan" data={{ steps: ["draft", "ship"] }} renderers={renderers} />,
  );
  expect(screen.container.querySelector("pre")?.textContent).toBe(
    JSON.stringify({ steps: ["draft", "ship"] }, null, 2),
  );
});

test("a kind named for something every object has still falls back", () => {
  expect(rendererFor("toString", renderers)).toBe(json);
  expect(rendererFor("constructor", new Map())).toBe(json);
});

test("a Markdown field's HTML never renders", async () => {
  const screen = await render(
    <ArtifactContent kind="note" data={{ text: "<b>bold</b>" }} renderers={renderers} />,
  );
  expect(screen.container.querySelector("b")).toBeNull();
});

test("a renderer says what its changes are read from, and how finely", () => {
  expect(markdown("body").text({ body: "Hello", text: "no" })).toBe("Hello");
  expect(markdown().text({ text: 3 })).toBe("");
  expect(markdown().diff).toBe("words");
  expect(json.text({ a: 1 })).toBe('{\n  "a": 1\n}');
  expect(json.diff).toBe("lines");
});

const launch: Change[] = [
  { kind: "same", text: "Launch on " },
  { kind: "removed", text: "Monday" },
  { kind: "added", text: "Tuesday" },
  { kind: "same", text: "." },
];

test("a diff marks what was added and removed, for eyes and for screen readers", async () => {
  const screen = await render(<Diff changes={launch} />);
  const added = screen.container.querySelector("ins");
  const removed = screen.container.querySelector("del");
  expect(added?.textContent).toBe("added: Tuesday");
  expect(removed?.textContent).toBe("removed: Monday");
  const style = (element: Element | null) => getComputedStyle(element as Element);
  expect(style(added).backgroundColor).toBe(token("wash"));
  expect(style(added).textDecorationColor).toBe(token("accent"));
  expect(contrast(style(added).color, style(added).backgroundColor)).toBeGreaterThanOrEqual(7);
  expect(style(removed).textDecorationLine).toBe("line-through");
  expect(contrast(style(removed).color, token("paper"))).toBeGreaterThanOrEqual(4.5);
  await expect.element(screen.getByText("Launch on")).toBeVisible();
});

test("a diff takes a caller's classes", async () => {
  const screen = await render(<Diff changes={launch} className="text-xs" />);
  const diff = screen.container.querySelector("p");
  expect(diff?.classList).toContain("text-xs");
  expect(diff?.classList).not.toContain("text-sm");
});

test("changes too large to compare say so", async () => {
  const screen = await render(<Diff changes={null} />);
  await expect.element(screen.getByText("Too large to compare.")).toBeVisible();
});

test("a title is the first line's words, without Markdown's marks, one line, and cut", () => {
  expect(markdown().title({ text: "# Launch **plan**\n\nOn [Tuesday](https://x.test)." })).toBe(
    "Launch plan",
  );
  expect(plainTitle("\n\n- `code` _in_ a list")).toBe("code in a list");
  expect(plainTitle("> quoted\n")).toBe("quoted");
  expect(plainTitle("a   b\t c")).toBe("a b c");
  expect(plainTitle("---\n***\nafter the rules")).toBe("after the rules");
  const long = plainTitle("x".repeat(500)) ?? "";
  expect([...long]).toHaveLength(LONGEST_TITLE);
  expect(long.endsWith("…")).toBe(true);
  // A letter outside the basic plane, past the cut, isn't split in half; an emoji alone is no title.
  expect(plainTitle("𝒜".repeat(200))).toBe(`${"𝒜".repeat(LONGEST_TITLE - 1)}…`);
  expect(plainTitle("😀😀")).toBeNull();
});

test("a title is null, not an error, where the data hold none or odd ones", () => {
  expect(plainTitle("")).toBeNull();
  expect(plainTitle("   \n\n")).toBeNull();
  expect(plainTitle("# \n---")).toBeNull();
  expect(markdown().title({})).toBeNull();
  expect(markdown().title({ text: 3 })).toBeNull();
  expect(markdown("body").title({ body: "Plans\nmore" })).toBe("Plans");
  expect(json.title({ title: "Q3 numbers" })).toBe("Q3 numbers");
  expect(json.title({ title: 7 })).toBeNull();
  expect(json.title({ title: { nested: true } })).toBeNull();
  expect(json.title({ name: "no title field" })).toBeNull();
  expect(json.title({})).toBeNull();
});
