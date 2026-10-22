import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Badge } from "./badge";
import { Heading } from "./heading";
import { SectionTitle } from "./section-title";
import { contrast } from "./test/colours";

test("a heading sits at the outline's level and weighs what its look says", async () => {
  const screen = await render(
    <>
      <SectionTitle>Section</SectionTitle>
      <Heading level={3} look="subsection">
        Part
      </Heading>
      <Heading level={4} look="label">
        Card
      </Heading>
    </>,
  );
  await expect.element(screen.getByRole("heading", { level: 2, name: "Section" })).toBeVisible();
  const part = screen.getByRole("heading", { level: 3, name: "Part" }).element();
  const card = screen.getByRole("heading", { level: 4, name: "Card" }).element();
  const size = (element: Element) => Number.parseFloat(getComputedStyle(element).fontSize);
  const section = screen.getByRole("heading", { level: 2 }).element();
  expect(size(section)).toBeGreaterThan(size(part));
  expect(size(part)).toBeGreaterThan(size(card));
});

test("a badge's words read on its fill, and it has an edge in either tone", async () => {
  const screen = await render(
    <>
      <Badge>Latest</Badge>
      <Badge tone="accent">Recommended</Badge>
    </>,
  );
  for (const word of ["Latest", "Recommended"]) {
    const style = getComputedStyle(screen.getByText(word).element());
    expect(style.borderTopWidth).toBe("1px");
    expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
  }
});
