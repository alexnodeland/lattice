import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { SegmentedFilter } from "./segmented-filter";
import { contrast, token } from "./test/colours";

const SEGMENTS = [
  { value: "all", label: "All", count: 7 },
  { value: "you", label: "Needs you", count: 2 },
  { value: "turns", label: "Turns" },
] as const;

type Shown = (typeof SEGMENTS)[number]["value"];

test("a filter is a named radio group, each choice said with its count", async () => {
  const screen = await render(
    <SegmentedFilter<Shown> label="Show" segments={SEGMENTS} value="all" onValueChange={vi.fn()} />,
  );
  const group = screen.getByRole("radiogroup", { name: "Show" });
  await expect.element(group.getByRole("radio", { name: "All, 7" })).toBeChecked();
  await expect.element(group.getByRole("radio", { name: "Needs you, 2" })).not.toBeChecked();
  await expect.element(group.getByRole("radio", { name: "Turns" })).not.toBeChecked();
});

test("the choice is pressed as every chosen control is: on the wash, in the working colour", async () => {
  const screen = await render(
    <SegmentedFilter<Shown> label="Show" segments={SEGMENTS} value="all" onValueChange={vi.fn()} />,
  );
  const style = getComputedStyle(screen.getByRole("radio", { name: "All, 7" }).element());
  expect(style.backgroundColor).toBe(token("wash"));
  expect(style.color).toBe(token("accent"));
  expect(style.borderTopColor).toBe(token("accent"));
  expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
});

test("choosing another hands it over", async () => {
  const chosen = vi.fn();
  const screen = await render(
    <SegmentedFilter<Shown> label="Show" segments={SEGMENTS} value="all" onValueChange={chosen} />,
  );
  await screen.getByRole("radio", { name: "Turns" }).click();
  expect(chosen).toHaveBeenCalledExactlyOnceWith("turns");
});

test("arrow keys move the choice", async () => {
  const chosen = vi.fn();
  const screen = await render(
    <SegmentedFilter<Shown> label="Show" segments={SEGMENTS} value="all" onValueChange={chosen} />,
  );
  await userEvent.tab();
  await expect.element(screen.getByRole("radio", { name: "All, 7" })).toHaveFocus();
  await userEvent.keyboard("{ArrowRight}");
  await expect.element(screen.getByRole("radio", { name: "Needs you, 2" })).toHaveFocus();
  expect(chosen).toHaveBeenCalledWith("you");
});
