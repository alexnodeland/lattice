import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { SectionTitle } from "./section-title";

test("a section's title is a second-level heading that can name its section", async () => {
  const screen = await render(
    <section aria-labelledby="revisions">
      <SectionTitle id="revisions">Revisions</SectionTitle>
    </section>,
  );
  await expect.element(screen.getByRole("heading", { level: 2, name: "Revisions" })).toBeVisible();
  await expect.element(screen.getByRole("region", { name: "Revisions" })).toBeVisible();
});
