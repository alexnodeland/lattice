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

test("an item named apart from its first cell is named so, as a row and as a card", async () => {
  const table = (
    <ItemTable
      caption="Grants"
      columns={[{ key: "role", label: "Role", cell: (grant) => grant.role }]}
      items={[{ role: "viewer", to: "bob" }]}
      keyOf={(grant) => grant.to}
      named={(grant) => `${grant.to} as ${grant.role}`}
      empty={{ title: "No grants", body: "None yet." }}
    />
  );
  await page.viewport(1024, 768);
  onTestFinished(() => page.viewport(414, 896));
  const wide = await render(table);
  await expect.element(wide.getByRole("row", { name: "bob as viewer" })).toBeVisible();
  await page.viewport(414, 896);
  await expect.element(wide.getByRole("listitem", { name: "bob as viewer" })).toBeVisible();
});

test("named by a heading beside it, the table, and on a phone the list, take its name", async () => {
  const table = (
    <div>
      <h2 id="workspace-notes">Workspace notes</h2>
      <ItemTable
        labelledBy="workspace-notes"
        columns={[
          { key: "to", label: "To", cell: (grant) => grant.to, width: "40%" },
          { key: "role", label: "Role", cell: (grant) => grant.role },
        ]}
        items={[{ to: "bob", role: "editor" }]}
        keyOf={(grant) => grant.to}
        empty={{ title: "No grants", body: "None yet." }}
      />
    </div>
  );
  await page.viewport(1024, 768);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(table);
  const wide = screen.getByRole("table", { name: "Workspace notes" });
  await expect.element(wide).toBeVisible();
  // A column given a width is laid out to it, so stacked tables line up.
  expect(getComputedStyle(wide.element()).tableLayout).toBe("fixed");
  await page.viewport(414, 896);
  await expect.element(screen.getByRole("list", { name: "Workspace notes" })).toBeVisible();
});

test("on a phone a card leaves out what its item has nothing for, label and all", async () => {
  await page.viewport(390, 844);
  const screen = await render(
    <ItemTable
      caption="Traces"
      columns={[
        { key: "trace", label: "Trace", cell: (trace) => trace.id },
        { key: "took", label: "Took", cell: (trace) => trace.took },
      ]}
      items={[
        { id: "a1", took: "47 ms" },
        { id: "b2", took: null },
      ]}
      keyOf={(trace) => trace.id}
      empty={{ title: "No traces", body: "None yet." }}
    />,
  );
  const list = screen.getByRole("list", { name: "Traces" });
  await expect.element(list.getByRole("listitem", { name: "a1" }).getByText("Took")).toBeVisible();
  expect(list.getByRole("listitem", { name: "b2" }).getByText("Took").elements()).toHaveLength(0);
});

test("a card's heading sits one level under what names the table: the page's, or the heading named", async () => {
  await page.viewport(390, 844);
  const screen = await render(
    <>
      <Members />
      <h2 id="notes">Workspace notes</h2>
      <ItemTable
        labelledBy="notes"
        columns={[{ key: "to", label: "To", cell: (grant: { to: string }) => grant.to }]}
        items={[{ to: "bob" }]}
        keyOf={(grant) => grant.to}
        empty={{ title: "No grants", body: "None yet." }}
      />
      <ItemTable
        caption="Deep"
        level={4}
        columns={[{ key: "to", label: "To", cell: (grant: { to: string }) => grant.to }]}
        items={[{ to: "dee" }]}
        keyOf={(grant) => grant.to}
        empty={{ title: "No grants", body: "None yet." }}
      />
    </>,
  );
  await expect.element(screen.getByRole("heading", { level: 2, name: "ci" })).toBeVisible();
  await expect.element(screen.getByRole("heading", { level: 3, name: "bob" })).toBeVisible();
  await expect.element(screen.getByRole("heading", { level: 4, name: "dee" })).toBeVisible();
});
