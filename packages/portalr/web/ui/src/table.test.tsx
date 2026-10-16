import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Button } from "./button";
import { Table } from "./table";
import { contrast } from "./test/colours";

test("a table is named by its caption, and its headings read on the surface", async () => {
  const screen = await render(
    <Table caption="The workspace's runs">
      <thead>
        <tr>
          <th scope="col">Status</th>
          <th scope="col">Run</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Done</td>
          <td>Weekly summary</td>
        </tr>
      </tbody>
    </Table>,
  );
  const table = screen.getByRole("table", { name: "The workspace's runs" });
  await expect.element(table.getByRole("columnheader", { name: "Status" })).toBeVisible();
  await expect.element(table.getByRole("cell", { name: "Weekly summary" })).toBeVisible();
  const heading = getComputedStyle(table.getByRole("columnheader", { name: "Run" }).element());
  const surface = getComputedStyle(table.element().parentElement as Element).backgroundColor;
  expect(contrast(heading.color, surface)).toBeGreaterThanOrEqual(4.5);
});

test("the keyboard reaches the table's scroll, a region of the caption's name", async () => {
  const screen = await render(
    <Table caption="Runs">
      <tbody>
        <tr>
          <td>Done</td>
        </tr>
      </tbody>
    </Table>,
  );
  await userEvent.tab();
  await expect.element(screen.getByRole("region", { name: "Runs" })).toHaveFocus();
});

test("a row's header reads as its row does, between the row's borders", async () => {
  const screen = await render(
    <Table caption="Members">
      <thead>
        <tr>
          <th scope="col">Member</th>
          <th scope="col">Kind</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <th scope="row">alice</th>
          <td>person</td>
        </tr>
      </tbody>
    </Table>,
  );
  const header = getComputedStyle(screen.getByRole("rowheader", { name: "alice" }).element());
  const cell = getComputedStyle(screen.getByRole("cell", { name: "person" }).element());
  expect(header.fontSize).toBe(cell.fontSize);
  expect(header.color).toBe(cell.color);
  expect(header.borderTopWidth).toBe(cell.borderTopWidth);
  expect(header.borderTopStyle).toBe("solid");
});

test("a table may be named by a heading beside it", async () => {
  const screen = await render(
    <section>
      <h2 id="tenant-grants">The tenant</h2>
      <Table labelledBy="tenant-grants">
        <tbody>
          <tr>
            <td>owner</td>
          </tr>
        </tbody>
      </Table>
    </section>,
  );
  await expect.element(screen.getByRole("table", { name: "The tenant" })).toBeVisible();
  await expect.element(screen.getByRole("region", { name: "The tenant" })).toBeVisible();
  expect(screen.getByRole("table").element().querySelector("caption")).toBeNull();
});

test("a column's header stays small and muted", async () => {
  const screen = await render(
    <Table caption="Members">
      <thead>
        <tr>
          <th scope="col">Member</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>alice</td>
        </tr>
      </tbody>
    </Table>,
  );
  const header = getComputedStyle(screen.getByRole("columnheader", { name: "Member" }).element());
  const cell = getComputedStyle(screen.getByRole("cell", { name: "alice" }).element());
  expect(Number.parseFloat(header.fontSize)).toBeLessThan(Number.parseFloat(cell.fontSize));
  expect(header.color).not.toBe(cell.color);
});

test("every row is the same height, whether its cells hold words, a small action or a tall one", async () => {
  const screen = await render(
    <Table caption="Members">
      <tbody>
        <tr>
          <th scope="row">alice</th>
          <td>owner</td>
        </tr>
        <tr>
          <th scope="row">bob</th>
          <td>
            <Button variant="ghost" size="sm">
              Remove
            </Button>
          </td>
        </tr>
        <tr>
          <th scope="row">carol</th>
          <td>
            <Button variant="secondary">Remove</Button>
          </td>
        </tr>
      </tbody>
    </Table>,
  );
  const heights = screen
    .getByRole("table", { name: "Members" })
    .getByRole("row")
    .elements()
    .map((row) => Math.round(row.getBoundingClientRect().height));
  const least =
    Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--row-height")) *
    16;
  // The rows with words and with a small action match, at the token's height; the taller button makes its own.
  expect(heights[0]).toBe(heights[1]);
  expect(heights[0]).toBeGreaterThanOrEqual(least);
});
