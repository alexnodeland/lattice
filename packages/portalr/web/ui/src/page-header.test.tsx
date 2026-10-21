import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { PageHeader } from "./page-header";

test("a page header's title is the page's one heading, with its way back, its line and its actions", async () => {
  const screen = await render(
    <PageHeader
      title="Launch plan"
      breadcrumbs={[{ label: "Threads", href: "#threads" }]}
      meta="Started by you"
      actions={<button type="button">More</button>}
    />,
  );
  await expect
    .element(screen.getByRole("heading", { level: 1, name: "Launch plan" }))
    .toBeVisible();
  await expect.element(screen.getByRole("link", { name: "Threads" })).toBeVisible();
  await expect.element(screen.getByText("Started by you")).toBeVisible();
  await expect.element(screen.getByRole("button", { name: "More" })).toBeVisible();
});

test("a page header without extras is its heading alone", async () => {
  const screen = await render(<PageHeader title="Runs" />);
  expect(screen.container.querySelectorAll("a, button, nav, p")).toHaveLength(0);
});

test("a page header's heading can name the region around it", async () => {
  const screen = await render(
    <section aria-labelledby="note">
      <PageHeader title="art_1" id="note" />
    </section>,
  );
  await expect.element(screen.getByRole("region", { name: "art_1" })).toBeVisible();
});
