import { expect, test } from "vitest";
import { page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { AppShell } from "./app-shell";
import { Button } from "./button";
import { Table } from "./table";

function Members({ ui }: { ui: "app" | "admin" }) {
  return (
    <AppShell ui={ui} home={<a href="#home" />} switcher={<span>s</span>} account={<span>a</span>}>
      <Table caption="Members">
        <tbody>
          <tr>
            <th scope="row">alice</th>
            <td>owner</td>
          </tr>
          <tr>
            <th scope="row">bob</th>
            <td>
              <Button variant="danger-soft" size="sm">
                Remove
              </Button>
            </td>
          </tr>
        </tbody>
      </Table>
    </AppShell>
  );
}

const rows = (screen: Awaited<ReturnType<typeof render>>) =>
  screen
    .getByRole("table", { name: "Members" })
    .getByRole("row")
    .elements()
    .map((row) => Math.round(row.getBoundingClientRect().height));

test("admin's tables are compact: 36px rows, 13px words, and a small action still fits", async () => {
  await page.viewport(1280, 800);
  const screen = await render(<Members ui="admin" />);
  expect(rows(screen)).toEqual([36, 36]);
  const cell = screen.getByRole("cell", { name: "owner" }).element();
  expect(getComputedStyle(cell).fontSize).toBe("13px");
});

test("the app's are comfortable: 44px rows and 14px words, though the same table", async () => {
  await page.viewport(1280, 800);
  const screen = await render(<Members ui="app" />);
  expect(rows(screen)).toEqual([44, 44]);
  const cell = screen.getByRole("cell", { name: "owner" }).element();
  expect(getComputedStyle(cell).fontSize).toBe("14px");
});

test("only admin's frame says it is compact", async () => {
  await render(<Members ui="app" />);
  expect(document.querySelector("[data-density]")).toBeNull();
});
