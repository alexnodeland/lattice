import { expect, onTestFinished, test } from "vitest";
import { page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { ItemTable } from "./item-table";

const members = [
  { id: "alice", kind: "person" },
  { id: "ci", kind: "service principal" },
];

function Members() {
  return (
    <ItemTable
      caption="Members"
      columns={[
        { key: "member", label: "Member", cell: (member) => member.id },
        { key: "kind", label: "Kind", cell: (member) => member.kind },
      ]}
      items={members}
      keyOf={(member) => member.id}
      actions={(member) => <button type="button">Remove {member.id}</button>}
      empty={{ title: "No members yet", body: "People appear here once invited." }}
    />
  );
}

test("on a wide screen the items are a table's rows, each named by its first column", async () => {
  await page.viewport(1024, 768);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(<Members />);
  const table = screen.getByRole("table", { name: "Members" });
  await expect.element(table.getByRole("row", { name: "ci" })).toBeVisible();
  await expect.element(table.getByRole("rowheader", { name: "ci" })).toBeVisible();
  await expect.element(table.getByRole("columnheader", { name: "Kind" })).toBeVisible();
  await expect.element(screen.getByRole("list", { name: "Members" })).not.toBeInTheDocument();
});

test("on a phone they're cards, each headed and named by its first column, and no table", async () => {
  await page.viewport(390, 844);
  const screen = await render(<Members />);
  const card = screen.getByRole("list", { name: "Members" }).getByRole("listitem", { name: "ci" });
  await expect.element(card.getByRole("heading", { name: "ci" })).toBeVisible();
  await expect.element(card.getByText("service principal")).toBeVisible();
  await expect.element(card.getByRole("button", { name: "Remove ci" })).toBeVisible();
  await expect.element(screen.getByRole("table")).not.toBeInTheDocument();
});

test("no items says so, as an empty state", async () => {
  const screen = await render(
    <ItemTable
      caption="Keys"
      columns={[{ key: "key", label: "Key", cell: (key: string) => key }]}
      items={[]}
      keyOf={(key) => key}
      empty={{ title: "No keys yet", body: "A key appears here once issued." }}
    />,
  );
  await expect.element(screen.getByRole("heading", { name: "No keys yet" })).toBeVisible();
});
