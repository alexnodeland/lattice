import { useRef, useState } from "react";
import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Button } from "./button";
import { Dialog } from "./dialog";

function Opened({ aimed = false }: { aimed?: boolean }) {
  const [open, setOpen] = useState(false);
  const person = useRef<HTMLInputElement>(null);
  const back = useRef<HTMLButtonElement>(null);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Share…</Button>
      <Button ref={back}>Thread actions</Button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Share the thread"
        description="Who may see it, and what they may do."
        {...(aimed && { initialFocus: person, finalFocus: back })}
      >
        <Button>Revoke</Button>
        <input aria-label="Person" ref={person} />
      </Dialog>
    </>
  );
}

test("a dialog is named by its title, described, and closed by its button", async () => {
  const screen = await render(<Opened />);
  await screen.getByRole("button", { name: "Share…" }).click();
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  await expect.element(dialog).toHaveAccessibleDescription("Who may see it, and what they may do.");
  await expect.element(dialog.getByRole("button", { name: "Revoke" })).toHaveFocus();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
  await expect.element(screen.getByRole("button", { name: "Share…" })).toHaveFocus();
});

test("focus starts where it's aimed, and returns where it's sent", async () => {
  const screen = await render(<Opened aimed />);
  await screen.getByRole("button", { name: "Share…" }).click();
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  await expect.element(dialog.getByRole("textbox", { name: "Person" })).toHaveFocus();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect.element(screen.getByRole("button", { name: "Thread actions" })).toHaveFocus();
});

test("a dialog is modal: named so, and Tab goes round its own controls", async () => {
  function Shown() {
    const [open, setOpen] = useState(true);
    return (
      <>
        <button type="button">Behind</button>
        <Dialog open={open} onOpenChange={setOpen} title="Share the thread">
          <button type="button">One</button>
        </Dialog>
      </>
    );
  }
  const screen = await render(<Shown />);
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  await expect.element(dialog).toHaveAttribute("aria-modal", "true");
  // Once its first focus has landed in it, as it opens.
  await expect.poll(() => dialog.element().contains(document.activeElement)).toBe(true);
  // Never, even for a frame, on Base UI's guards outside the dialog.
  const guarded: Element[] = [];
  const onGuard = (event: FocusEvent) => {
    if (event.target instanceof Element && event.target.hasAttribute("data-base-ui-focus-guard")) {
      guarded.push(event.target);
    }
  };
  document.addEventListener("focusin", onGuard);
  for (const shift of [false, false, false, false, false, true, true, true, true]) {
    await userEvent.tab({ shift });
    expect(dialog.element().contains(document.activeElement)).toBe(true);
  }
  document.removeEventListener("focusin", onGuard);
  expect(guarded).toEqual([]);
});
