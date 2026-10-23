import { type Names, namesOf } from "@portalr/client";
import { choose, optionsOf } from "@portalr/ui/testing";
import { useRef, useState } from "react";
import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { type Role, ShareDialog } from "./share-dialog";

const on = { kind: "thread", workspace: "notes", id: "thr_1" } as const;
const erin = { role: "editor", on, tenant: "acme", to: { kind: "user", id: "erin" } } as const;
const done = { outcome: "done", result: { seq: 1 } } as never;

function Opened({
  onGrant = vi.fn(async () => done),
  onRevoke = vi.fn(async () => done),
  grants = [erin],
  people = ["bob", "vera"],
  names,
}: {
  onGrant?: (person: string, role: Role) => Promise<never>;
  onRevoke?: () => Promise<never>;
  grants?: readonly (typeof erin)[] | null;
  people?: readonly string[];
  names?: Names;
}) {
  const [open, setOpen] = useState(false);
  const back = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button type="button" ref={back} onClick={() => setOpen(true)}>
        Thread actions
      </button>
      <ShareDialog
        open={open}
        onOpenChange={setOpen}
        grants={grants}
        people={people}
        {...(names && { names })}
        canRevoke
        onGrant={onGrant}
        onRevoke={onRevoke}
        finalFocus={back}
      />
    </>
  );
}

test("the dialog lists who holds a role, starts at the person, and returns to the menu", async () => {
  const screen = await render(<Opened />);
  await screen.getByRole("button", { name: "Thread actions" }).click();
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  const row = dialog.getByRole("listitem");
  await expect.element(row.getByText("erin", { exact: true })).toBeVisible();
  await expect.element(row.getByText("editor", { exact: true })).toBeVisible();
  // A row shows "Revoke", and is named by whom and what it revokes.
  await expect.element(dialog.getByRole("button", { name: "Revoke erin as editor" })).toBeVisible();
  await expect.element(dialog.getByRole("combobox", { name: "Person" })).toHaveFocus();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect.element(screen.getByRole("button", { name: "Thread actions" })).toHaveFocus();
});

test("sharing sends the person and the role, and a refusal is said for the form", async () => {
  const onGrant = vi.fn(
    async () => ({ outcome: "refused", status: 403, reasons: ["no"] }) as never,
  );
  const screen = await render(<Opened onGrant={onGrant} />);
  await screen.getByRole("button", { name: "Thread actions" }).click();
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  await choose(dialog, "Person", "vera");
  await choose(dialog, "Role", "editor");
  await dialog.getByRole("button", { name: "Share", exact: true }).click();
  expect(onGrant).toHaveBeenCalledExactlyOnceWith("vera", "editor");
  await expect.element(dialog.getByRole("alert")).toHaveTextContent("Not shared: no");
});

test("revoking sends the grant as it is", async () => {
  const onRevoke = vi.fn(async () => done);
  const screen = await render(<Opened onRevoke={onRevoke} />);
  await screen.getByRole("button", { name: "Thread actions" }).click();
  await screen.getByRole("button", { name: "Revoke erin as editor" }).click();
  await screen.getByRole("alertdialog").getByRole("button", { name: "Revoke the role" }).click();
  expect(onRevoke).toHaveBeenCalledExactlyOnceWith(erin);
});

test("each empty state says why", async () => {
  const screen = await render(<Opened grants={null} people={[]} />);
  await screen.getByRole("button", { name: "Thread actions" }).click();
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  await expect
    .element(dialog.getByText("You may share it, but not see who holds a role on it."))
    .toBeVisible();
  await expect.element(dialog.getByText(/There's no one else to share it with/)).toBeVisible();
  await expect.element(dialog.getByRole("form")).not.toBeInTheDocument();
});

const VERA = "3f2a91c4-1111-4222-8333-444455556666";
const GONE = "c0ffee00-1111-4222-8333-444455556666";
const named: Names = namesOf({ [VERA]: "vera@acme.test", erin: "erin@acme.test" });

test("people are offered and listed by their email, a short id where the server names none", async () => {
  const screen = await render(<Opened people={[VERA, GONE]} names={named} grants={[erin]} />);
  await screen.getByRole("button", { name: "Thread actions" }).click();
  const people = await optionsOf(screen, "Person");
  expect(people).toContain("vera@acme.test");
  expect(people).toContain("c0ffee00…");
  const holders = screen.getByRole("list", { name: "People with access" });
  await expect.element(holders).toBeVisible();
  await expect.element(holders.getByText("erin@acme.test", { exact: true })).toBeVisible();
  await expect.element(holders.getByText("editor", { exact: true })).toBeVisible();
});

test("what is sent for a person is their id, not their email", async () => {
  const onGrant = vi.fn(async () => done);
  const screen = await render(<Opened people={[VERA]} names={named} onGrant={onGrant} />);
  await screen.getByRole("button", { name: "Thread actions" }).click();
  await screen.getByRole("button", { name: "Share", exact: true }).click();
  await vi.waitFor(() => expect(onGrant).toHaveBeenCalledWith(VERA, "viewer"));
});

test("the revoke dialog names a person as the list does", async () => {
  const screen = await render(<Opened names={named} />);
  await screen.getByRole("button", { name: "Thread actions" }).click();
  await screen.getByRole("button", { name: "Revoke erin@acme.test as editor" }).click();
  await expect
    .element(screen.getByRole("alertdialog", { name: "Revoke erin@acme.test's editor role?" }))
    .toBeVisible();
});

test("a name arriving does not close an open revoke confirmation", async () => {
  const screen = await render(<Opened />);
  await screen.getByRole("button", { name: "Thread actions" }).click();
  await screen.getByRole("button", { name: "Revoke erin as editor" }).click();
  const confirmation = screen.getByRole("alertdialog", { name: "Revoke erin's editor role?" });
  await expect.element(confirmation).toBeVisible();
  // The email arrives while the confirmation is open: the row is the same row.
  await screen.rerender(<Opened names={named} />);
  await expect
    .element(screen.getByRole("alertdialog", { name: "Revoke erin@acme.test's editor role?" }))
    .toBeVisible();
});

test("people are offered in the order of what is shown", async () => {
  const screen = await render(
    <Opened
      people={[VERA, GONE, "zed"]}
      names={namesOf({ [VERA]: "zoe@acme.test", zed: "adam@acme.test" })}
    />,
  );
  await screen.getByRole("button", { name: "Thread actions" }).click();
  const options = await optionsOf(screen, "Person");
  expect(options.filter((option) => option?.includes("@") || option?.endsWith("…"))).toEqual([
    "adam@acme.test",
    "c0ffee00…",
    "zoe@acme.test",
  ]);
});

test("Share is modal: Tab and Shift+Tab go round its own controls, Close among them", async () => {
  const screen = await render(<Opened />);
  await screen.getByRole("button", { name: "Thread actions" }).click();
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  await expect.element(dialog).toHaveAttribute("aria-modal", "true");
  // Once its first focus has landed in it, as it opens.
  await expect.poll(() => dialog.element().contains(document.activeElement)).toBe(true);
  const inside = () => dialog.element().contains(document.activeElement);
  const seen = new Set<string>();
  for (let step = 0; step < 8; step++) {
    await userEvent.tab();
    expect(inside()).toBe(true);
    seen.add(document.activeElement?.textContent ?? "");
  }
  expect(seen.has("Close")).toBe(true);
  for (let step = 0; step < 8; step++) {
    await userEvent.tab({ shift: true });
    expect(inside()).toBe(true);
  }
});
