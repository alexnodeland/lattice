import { expect, test } from "vitest";
import { page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Tracker } from "./tracker";

const levels = [
  { key: "none", name: "Nothing spent" },
  { key: "under", name: "Under its share" },
  { key: "near", name: "Near its share" },
  { key: "over", name: "Over its share" },
];

test("a tracker names its levels, marks each block, and gives its figures as a table", async () => {
  await page.viewport(1024, 768);
  const screen = await render(
    <Tracker
      label="Spend against the budget's share"
      index="Day (UTC)"
      figure="Spend"
      levels={levels}
      blocks={[
        { key: "a", name: "10-11", level: 0, figure: "$0.00" },
        { key: "b", name: "10-12", level: 1, figure: "$1.00" },
        { key: "c", name: "10-13", level: 3, figure: "$9.00" },
      ]}
    />,
  );
  const figure = screen.getByRole("figure", { name: "Spend against the budget's share" });
  await expect.element(figure).toBeVisible();
  expect(
    figure
      .getByRole("listitem")
      .elements()
      .map((item) => item.textContent),
  ).toEqual(levels.map((level) => level.name));
  // Each block is marked by its level, and named in its title.
  const blocks = [...document.querySelectorAll("[data-level]")];
  expect(blocks.map((block) => block.getAttribute("data-level"))).toEqual(["0", "1", "3"]);
  expect(blocks[2]?.getAttribute("title")).toBe("10-13: $9.00, Over its share");
  // Past the second, a level has a pattern, so it isn't told by its colour alone.
  const marks = blocks.map((block) => (block.firstElementChild as HTMLElement).style.background);
  expect(marks[2]).toContain("repeating-linear-gradient");
  expect(marks[1]).not.toContain("gradient");
  await figure.getByText("Show the figures").click();
  await expect
    .element(figure.getByRole("row", { name: "10-13" }))
    .toHaveTextContent("10-13$9.00Over its share");
});

test("a block past the levels is marked as the least, and named with none", async () => {
  await render(
    <Tracker
      label="Odd"
      index="Day"
      figure="Spend"
      levels={levels.slice(0, 1)}
      blocks={[{ key: "a", name: "10-11", level: 7, figure: "$1.00" }]}
    />,
  );
  const block = document.querySelector("[data-level]");
  expect(block?.getAttribute("title")).toBe("10-11: $1.00");
  const blockMark = document.querySelector<HTMLElement>("[data-level] > div");
  expect(blockMark?.style.background).toBe("var(--line)");
});
