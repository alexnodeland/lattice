import { useState } from "react";
import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Button } from "./button";
import { Dialog } from "./dialog-box";

function Opened() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Share…</Button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Share the thread"
        description="Who may see it, and what they may do."
      >
        <p>Bob, viewer</p>
      </Dialog>
    </>
  );
}

test("a dialog is named by its title, described, and closed by its button", async () => {
  const screen = await render(<Opened />);
  await screen.getByRole("button", { name: "Share…" }).click();
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  await expect.element(dialog).toHaveAccessibleDescription("Who may see it, and what they may do.");
  await expect.element(dialog.getByText("Bob, viewer")).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
  await expect.element(screen.getByRole("button", { name: "Share…" })).toHaveFocus();
});
