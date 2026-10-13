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
        { label: "Member", cell: (member) => member.id },
        { label: "Kind", cell: (member) => member.kind },
      ]}
      items={members}
      keyOf={(member) => member.id}
      actions={(member) => <button type="button">Remove {member.id}</button>}
      empty="No members yet."
    />
  );
}

test("on a wide screen the items are a table's rows, each headed by its first column", async () => {
  await page.viewport(1024, 768);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(<Members />);
  const table = screen.getByRole("table", { name: "Members" });
  await expect.element(table.getByRole("rowheader", { name: "ci" })).toBeVisible();
  await expect.element(table.getByRole("columnheader", { name: "Kind" })).toBeVisible();
  await expect.element(screen.getByRole("list", { name: "Members" })).not.toBeInTheDocument();
});

test("on a phone they're cards, each with its labels and its actions, and no table", async () => {
  await page.viewport(390, 844);
  const screen = await render(<Members />);
  const cards = screen.getByRole("list", { name: "Members" }).getByRole("listitem");
  await expect.element(cards.nth(1)).toHaveTextContent("ciKindservice principalRemove ci");
  await expect.element(screen.getByRole("table")).not.toBeInTheDocument();
});

test("no items says so", async () => {
  const screen = await render(
    <ItemTable
      caption="Keys"
      columns={[{ label: "Key", cell: (key: string) => key }]}
      items={[]}
      keyOf={(key) => key}
      empty="No keys yet."
    />,
  );
  await expect.element(screen.getByText("No keys yet.")).toBeVisible();
});
