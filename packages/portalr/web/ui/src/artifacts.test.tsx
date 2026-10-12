import type { Change } from "@portalr/client";
import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { ArtifactContent, Diff, json, markdown, rendererFor } from "./artifacts";
import { token } from "./test/colours";

const renderers = { note: markdown() };

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
  expect(rendererFor("constructor", {})).toBe(json);
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
  expect(getComputedStyle(added as Element).color).toBe(token("accent"));
  expect(getComputedStyle(removed as Element).textDecorationLine).toBe("line-through");
  await expect.element(screen.getByText("Launch on")).toBeVisible();
});

test("a diff takes a caller's classes", async () => {
  const screen = await render(<Diff changes={launch} className="text-xs" />);
  const diff = screen.container.querySelector("p");
  expect(diff?.classList).toContain("text-xs");
  expect(diff?.classList).not.toContain("text-sm");
});
