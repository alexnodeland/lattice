import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
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
