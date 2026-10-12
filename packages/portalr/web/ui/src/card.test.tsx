import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Card } from "./card";
import { contrast, token } from "./test/colours";

test("a card sits on the surface, outlined, its text readable", async () => {
  const screen = await render(<Card>Approve publish?</Card>);
  const style = getComputedStyle(screen.getByText("Approve publish?").element());
  expect(style.backgroundColor).toBe(token("surface"));
  expect(style.borderTopColor).toBe(token("line"));
  expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(7);
});

test("a card renders as the element it is given, such as a named section", async () => {
  const screen = await render(
    <Card render={<section aria-label="Approve publish?" />}>The agent wants to publish.</Card>,
  );
  await expect.element(screen.getByRole("region", { name: "Approve publish?" })).toBeVisible();
});
