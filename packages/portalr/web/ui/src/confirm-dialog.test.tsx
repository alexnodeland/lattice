import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { ConfirmDialog } from "./confirm-dialog";
import { contrast, token } from "./test/colours";

function Archive({
  onConfirm = vi.fn(async () => undefined),
  typed,
}: {
  onConfirm?: () => Promise<unknown>;
  typed?: string;
}) {
  return (
    <ConfirmDialog
      label="Archive"
      title="Archive portalr:triage?"
      confirm="Archive the rule"
      onConfirm={onConfirm}
      {...(typed !== undefined && { typed })}
    >
      Version 3 stops running, and its runs stay in the log.
    </ConfirmDialog>
  );
}

test("the trigger opens an alert dialog that names what will be lost, the focus on Cancel", async () => {
  const screen = await render(<Archive />);
  await screen.getByRole("button", { name: "Archive" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Archive portalr:triage?" });
  await expect
    .element(dialog)
    .toHaveAccessibleDescription("Version 3 stops running, and its runs stay in the log.");
  await expect.element(dialog.getByRole("button", { name: "Cancel" })).toHaveFocus();
});

test("the action is in the danger colour, readably", async () => {
  const screen = await render(<Archive />);
  await screen.getByRole("button", { name: "Archive" }).click();
  const style = getComputedStyle(
    screen.getByRole("button", { name: "Archive the rule" }).element(),
  );
  expect(style.backgroundColor).toBe(token("danger"));
  expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
});

test("Escape and Cancel close it, doing nothing, and give the focus back", async () => {
  const onConfirm = vi.fn(async () => undefined);
  const screen = await render(<Archive onConfirm={onConfirm} />);
  const trigger = screen.getByRole("button", { name: "Archive" });
  await trigger.click();
  await userEvent.keyboard("{Escape}");
  await expect.element(screen.getByRole("alertdialog")).not.toBeInTheDocument();
  await expect.element(trigger).toHaveFocus();
  await trigger.click();
  await screen.getByRole("button", { name: "Cancel" }).click();
  await expect.element(screen.getByRole("alertdialog")).not.toBeInTheDocument();
  expect(onConfirm).not.toHaveBeenCalled();
});

test("confirming acts, then closes", async () => {
  const onConfirm = vi.fn(async () => undefined);
  const screen = await render(<Archive onConfirm={onConfirm} />);
  await screen.getByRole("button", { name: "Archive" }).click();
  await screen.getByRole("button", { name: "Archive the rule" }).click();
  expect(onConfirm).toHaveBeenCalledOnce();
  await expect.element(screen.getByRole("alertdialog")).not.toBeInTheDocument();
});

test("with a name to type, the action waits until it is typed", async () => {
  const onConfirm = vi.fn(async () => undefined);
  const screen = await render(<Archive onConfirm={onConfirm} typed="acme" />);
  await screen.getByRole("button", { name: "Archive" }).click();
  const field = screen.getByRole("textbox", { name: "Type acme to confirm" });
  await expect.element(field).toHaveFocus();
  const act = screen.getByRole("button", { name: "Archive the rule" });
  await expect.element(act).toBeDisabled();
  await field.fill("acm");
  await expect.element(act).toBeDisabled();
  await field.fill("acme");
  await expect.element(act).toBeEnabled();
  await act.click();
  expect(onConfirm).toHaveBeenCalledOnce();
});

test("with the name typed, Enter acts", async () => {
  const onConfirm = vi.fn(async () => undefined);
  const screen = await render(<Archive onConfirm={onConfirm} typed="acme" />);
  await screen.getByRole("button", { name: "Archive" }).click();
  await screen.getByRole("textbox", { name: "Type acme to confirm" }).fill("acme");
  await userEvent.keyboard("{Enter}");
  expect(onConfirm).toHaveBeenCalledOnce();
});

test("an action that fails keeps the dialog open, and says why", async () => {
  const onConfirm = vi.fn(async () => {
    throw new Error("The rule wasn't archived: it changed since you opened it.");
  });
  const screen = await render(<Archive onConfirm={onConfirm} />);
  await screen.getByRole("button", { name: "Archive" }).click();
  await screen.getByRole("button", { name: "Archive the rule" }).click();
  const dialog = screen.getByRole("alertdialog");
  await expect
    .element(dialog.getByRole("alert"))
    .toHaveTextContent("The rule wasn't archived: it changed since you opened it.");
});
