import { choose } from "@portalr/ui/testing";
import { useRef, useState } from "react";
import { expect, test, vi } from "vitest";
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
}: {
  onGrant?: (person: string, role: Role) => Promise<never>;
  onRevoke?: () => Promise<never>;
  grants?: readonly (typeof erin)[] | null;
  people?: readonly string[];
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
  await expect
    .element(dialog.getByRole("listitem"))
    .toHaveTextContent("erin editorRevoke erin as editor");
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
