import { useRef, useState } from "react";
import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { ConfirmDialog } from "./confirm-dialog";
import { contrast, token } from "./test/colours";
import { guardsFocused } from "./test/guards";

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

test("a failure that isn't an error says the kit's sentence, and goes to the console whole", async () => {
  const warned = vi.spyOn(console, "warn").mockImplementation(() => {});
  try {
    const onConfirm = vi.fn(async () => {
      throw { status: 503, detail: "<b>grantr</b> is down: password=hunter2" };
    });
    const screen = await render(<Archive onConfirm={onConfirm} />);
    await screen.getByRole("button", { name: "Archive" }).click();
    await screen.getByRole("button", { name: "Archive the rule" }).click();
    const alert = screen.getByRole("alertdialog").getByRole("alert");
    await expect.element(alert).toHaveTextContent("Something went wrong. Try again in a moment.");
    expect(alert.element().textContent).not.toContain("hunter2");
    expect(warned).toHaveBeenCalledOnce();
  } finally {
    warned.mockRestore();
  }
});

test("a trigger shows its words alone, and is named in full by what it acts on", async () => {
  const screen = await render(
    <ConfirmDialog
      label="Revoke"
      about="viewer from bob"
      look="danger-soft"
      size="sm"
      title="Revoke viewer from bob?"
      confirm="Revoke"
      onConfirm={async () => undefined}
    >
      bob loses what viewer holds there.
    </ConfirmDialog>,
  );
  const trigger = screen.getByRole("button", { name: "Revoke viewer from bob" });
  await expect.element(trigger).toBeVisible();
  // What it acts on is read aloud and not shown: a row of them says "Revoke", and no more.
  const aloud = trigger.element().querySelector(".sr-only");
  expect(aloud?.textContent).toBe(" viewer from bob");
  expect(getComputedStyle(aloud as Element).position).toBe("absolute");
  expect(getComputedStyle(trigger.element()).color).toBe(token("danger"));
});

test("the way out has words of its own where Cancel would stand beside another", async () => {
  const screen = await render(
    <ConfirmDialog
      label="Cancel"
      about="run run_1"
      dismiss="Keep running"
      title="Cancel this run?"
      confirm="Cancel run"
      onConfirm={async () => undefined}
    >
      It stops.
    </ConfirmDialog>,
  );
  await screen.getByRole("button", { name: "Cancel run run_1" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Cancel this run?" });
  await expect.element(dialog.getByRole("button", { name: "Keep running" })).toHaveFocus();
  await expect.element(dialog.getByRole("button", { name: "Cancel run" })).toBeVisible();
  await expect
    .element(dialog.getByRole("button", { name: "Cancel", exact: true }))
    .not.toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  await expect.element(dialog).not.toBeInTheDocument();
});

test("it can ask for a reason, which goes to the action, trimmed, and is asked for again each time", async () => {
  const onConfirm = vi.fn(async (_reason: string) => undefined);
  const screen = await render(
    <ConfirmDialog
      label="Skip"
      title="Skip this run?"
      confirm="Skip the run"
      asking="Reason (optional)"
      onConfirm={onConfirm}
    >
      The run is given up on.
    </ConfirmDialog>,
  );
  await screen.getByRole("button", { name: "Skip", exact: true }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Skip this run?" });
  await dialog.getByRole("textbox", { name: "Reason (optional)" }).fill("  a known outage  ");
  await dialog.getByRole("button", { name: "Skip the run" }).click();
  expect(onConfirm).toHaveBeenLastCalledWith("a known outage");
  // Reopened, it is empty, and a reason may be left out.
  await screen.getByRole("button", { name: "Skip", exact: true }).click();
  const again = screen.getByRole("alertdialog", { name: "Skip this run?" });
  await expect.element(again.getByRole("textbox", { name: "Reason (optional)" })).toHaveValue("");
  await again.getByRole("button", { name: "Skip the run" }).click();
  expect(onConfirm).toHaveBeenLastCalledWith("");
});

test("a reason is asked for only when it is asked for, and a calm action is not in the danger colour", async () => {
  const screen = await render(
    <ConfirmDialog
      label="Retry"
      title="Retry this run?"
      confirm="Retry the run"
      calm
      onConfirm={vi.fn(async () => undefined)}
    >
      It runs again.
    </ConfirmDialog>,
  );
  await screen.getByRole("button", { name: "Retry", exact: true }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Retry this run?" });
  expect(dialog.getByRole("textbox").elements()).toEqual([]);
  const calm = getComputedStyle(
    dialog.getByRole("button", { name: "Retry the run" }).element(),
  ).backgroundColor;
  await screen.unmount();
  const danger = await render(<Archive />);
  await danger.getByRole("button", { name: "Archive" }).click();
  const hot = getComputedStyle(
    danger.getByRole("alertdialog").getByRole("button", { name: "Archive the rule" }).element(),
  ).backgroundColor;
  expect(calm).not.toBe(hot);
});

test("however often it is submitted while it is under way, the action is sent once", async () => {
  let finish: () => void = () => undefined;
  const onConfirm = vi.fn(
    () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
  );
  const screen = await render(<Archive onConfirm={onConfirm} />);
  await screen.getByRole("button", { name: "Archive" }).click();
  const form = screen.getByRole("alertdialog").element().querySelector("form") as HTMLFormElement;
  form.requestSubmit();
  form.requestSubmit();
  form.requestSubmit();
  expect(onConfirm).toHaveBeenCalledTimes(1);
  finish();
  await expect.element(screen.getByRole("alertdialog")).not.toBeInTheDocument();
  expect(onConfirm).toHaveBeenCalledTimes(1);
});

test("a reason says how much of its room is used, and the dialog says when it opens and closes", async () => {
  const onOpenChange = vi.fn();
  const screen = await render(
    <ConfirmDialog
      label="Skip"
      title="Skip this run?"
      confirm="Skip the run"
      asking="Reason (optional)"
      onOpenChange={onOpenChange}
      onConfirm={async () => undefined}
    >
      The run is given up on.
    </ConfirmDialog>,
  );
  await screen.getByRole("button", { name: "Skip", exact: true }).click();
  expect(onOpenChange).toHaveBeenLastCalledWith(true);
  const dialog = screen.getByRole("alertdialog");
  await expect.element(dialog.getByText("0 of 500 characters")).toBeVisible();
  await dialog.getByRole("textbox", { name: "Reason (optional)" }).fill("abc");
  await expect.element(dialog.getByText("3 of 500 characters")).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  expect(onOpenChange).toHaveBeenLastCalledWith(false);
});

test("a dialog whose action is under way is not dismissed by Escape or Cancel, and is once it is done", async () => {
  let finish: () => void = () => undefined;
  const onConfirm = vi.fn(
    () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
  );
  const onOpenChange = vi.fn();
  const screen = await render(
    <ConfirmDialog
      label="Retry"
      title="Retry this run?"
      confirm="Retry the run"
      calm
      onOpenChange={onOpenChange}
      onConfirm={onConfirm}
    >
      It runs again.
    </ConfirmDialog>,
  );
  await screen.getByRole("button", { name: "Retry", exact: true }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Retry this run?" });
  await dialog.getByRole("button", { name: "Retry the run" }).click();
  await userEvent.keyboard("{Escape}");
  await dialog.getByRole("button", { name: "Cancel" }).click({ force: true });
  await expect.element(dialog).toBeVisible();
  expect(onOpenChange).not.toHaveBeenCalledWith(false);
  finish();
  await expect.element(dialog).not.toBeInTheDocument();
});

test("a dialog taken away with its trigger while open sends focus where the caller says", async () => {
  function Row() {
    const [gone, setGone] = useState(false);
    const heading = useRef<HTMLHeadingElement>(null);
    return (
      <>
        <h2 ref={heading} tabIndex={-1}>
          The runs
        </h2>
        {!gone && (
          <ConfirmDialog
            label="Retry"
            title="Retry this run?"
            confirm="Retry the run"
            calm
            returnTo={heading}
            onConfirm={async () => setGone(true)}
          >
            It runs again.
          </ConfirmDialog>
        )}
      </>
    );
  }
  const screen = await render(<Row />);
  await screen.getByRole("button", { name: "Retry", exact: true }).click();
  await screen
    .getByRole("alertdialog", { name: "Retry this run?" })
    .getByRole("button", { name: "Retry the run" })
    .click();
  await expect.element(screen.getByRole("heading", { name: "The runs" })).toHaveFocus();
});

test("a trigger can be disabled until what it acts on is filled in, and focus can go elsewhere when it closes", async () => {
  function Form() {
    const [filled, setFilled] = useState(false);
    const field = useRef<HTMLInputElement>(null);
    return (
      <>
        <input
          ref={field}
          aria-label="Name"
          onChange={(event) => setFilled(event.target.value !== "")}
        />
        <ConfirmDialog
          label="Create"
          title="Create it?"
          confirm="Create it"
          calm
          disabled={!filled}
          finalFocus={field}
          onConfirm={async () => setFilled(false)}
        >
          It is made.
        </ConfirmDialog>
      </>
    );
  }
  const screen = await render(<Form />);
  const trigger = screen.getByRole("button", { name: "Create", exact: true });
  await expect.element(trigger).toBeDisabled();
  await screen.getByRole("textbox", { name: "Name" }).fill("x");
  await expect.element(trigger).toBeEnabled();
  await trigger.click();
  await screen.getByRole("alertdialog").getByRole("button", { name: "Create it" }).click();
  await expect.element(screen.getByRole("alertdialog")).not.toBeInTheDocument();
  await expect.element(screen.getByRole("textbox", { name: "Name" })).toHaveFocus();
});

test("cancelling a dialog that sends focus elsewhere when done still returns it to the trigger", async () => {
  function Form() {
    const field = useRef<HTMLInputElement>(null);
    return (
      <>
        <input ref={field} aria-label="Name" />
        <ConfirmDialog
          label="Create"
          title="Create it?"
          confirm="Create it"
          calm
          finalFocus={field}
          onConfirm={async () => undefined}
        >
          It is made.
        </ConfirmDialog>
      </>
    );
  }
  const screen = await render(<Form />);
  await screen.getByRole("button", { name: "Create", exact: true }).click();
  await screen.getByRole("alertdialog").getByRole("button", { name: "Cancel" }).click();
  await expect.element(screen.getByRole("alertdialog")).not.toBeInTheDocument();
  await expect.element(screen.getByRole("button", { name: "Create", exact: true })).toHaveFocus();
});

test("Tab and Shift+Tab stay in it, never for a frame on a guard outside it", async () => {
  const screen = await render(<Archive />);
  await screen.getByRole("button", { name: "Archive" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Archive portalr:triage?" });
  await expect.element(dialog.getByRole("button", { name: "Cancel" })).toHaveFocus();
  const guarded = await guardsFocused(async () => {
    for (const shift of [false, false, false, true, true, true]) {
      await userEvent.tab({ shift });
      expect(dialog.element().contains(document.activeElement)).toBe(true);
    }
  });
  expect(guarded).toEqual([]);
});
