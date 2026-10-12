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

test("a filter is a named group, its choice pressed in the working colour", async () => {
  const screen = await render(
    <SegmentedFilter<Shown> label="Show" segments={SEGMENTS} value="all" onValueChange={vi.fn()} />,
  );
  const group = screen.getByRole("group", { name: "Show" });
  const all = group.getByRole("button", { name: "All 7" });
  await expect.element(all).toHaveAttribute("aria-pressed", "true");
  await expect
    .element(group.getByRole("button", { name: "Needs you 2" }))
    .toHaveAttribute("aria-pressed", "false");
  const style = getComputedStyle(all.element());
  expect(style.backgroundColor).toBe(token("accent"));
  expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
});

test("choosing another hands it over, and pressing the chosen one again keeps it", async () => {
  const chosen = vi.fn();
  const screen = await render(
    <SegmentedFilter<Shown> label="Show" segments={SEGMENTS} value="all" onValueChange={chosen} />,
  );
  await screen.getByRole("button", { name: "All 7" }).click();
  expect(chosen).not.toHaveBeenCalled();
  await screen.getByRole("button", { name: "Turns" }).click();
  expect(chosen).toHaveBeenCalledExactlyOnceWith("turns");
});

test("arrow keys move between the choices", async () => {
  const screen = await render(
    <SegmentedFilter<Shown> label="Show" segments={SEGMENTS} value="all" onValueChange={vi.fn()} />,
  );
  await userEvent.tab();
  await expect.element(screen.getByRole("button", { name: "All 7" })).toHaveFocus();
  await userEvent.keyboard("{ArrowRight}");
  await expect.element(screen.getByRole("button", { name: "Needs you 2" })).toHaveFocus();
});
