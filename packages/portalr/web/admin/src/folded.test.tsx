import { createPortal } from "react-dom";
import { expect, onTestFinished, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Folded, Toolbar } from "./folded";

test("a toolbar action opens its form in a card under the row, saying what is in effect while closed", async () => {
  const screen = await render(
    <Toolbar>
      <Folded title="Find" action="Find…" said="24 hours, thread thr_1">
        <input aria-label="Thread" />
      </Folded>
    </Toolbar>,
  );
  await expect.element(screen.getByText("24 hours, thread thr_1")).toBeVisible();
  expect(screen.getByRole("region", { name: "Find" }).elements()).toHaveLength(0);
  const action = screen.getByRole("button", { name: "Find…" });
  await expect.element(action).toHaveAttribute("aria-expanded", "false");
  await action.click();
  const region = screen.getByRole("region", { name: "Find" });
  await expect.element(region.getByRole("textbox", { name: "Thread" })).toBeVisible();
  await expect.element(action).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("24 hours, thread thr_1").elements()).toHaveLength(0);
  // Under the row: the form's top is below the button's bottom.
  expect(region.element().getBoundingClientRect().top).toBeGreaterThanOrEqual(
    action.element().getBoundingClientRect().bottom,
  );
});

test("an action opens at first where the page says, and as the page holds it", async () => {
  const screen = await render(
    <Toolbar>
      <Folded title="Grant a role" action="Grant…" defaultOpen>
        <input aria-label="Role" />
      </Folded>
    </Toolbar>,
  );
  await expect.element(screen.getByRole("textbox", { name: "Role" })).toBeVisible();
  await screen.rerender(
    <Toolbar>
      <Folded title="Change ops" action="Change…" open onOpenChange={() => {}}>
        <input aria-label="Members" />
      </Folded>
    </Toolbar>,
  );
  await expect.element(screen.getByRole("textbox", { name: "Members" })).toBeVisible();
});

test("opened by its button, a form's first field takes the focus; Escape closes it and gives the focus back", async () => {
  const screen = await render(
    <Toolbar>
      <Folded title="Invite" action="Invite…">
        <button type="button">Help</button>
        <input aria-label="Email" />
      </Folded>
    </Toolbar>,
  );
  const action = screen.getByRole("button", { name: "Invite…" });
  await action.click();
  // The field, not the button before it.
  await expect.element(screen.getByRole("textbox", { name: "Email" })).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  await expect.element(screen.getByRole("region", { name: "Invite" })).not.toBeInTheDocument();
  await expect.element(action).toHaveFocus();
});

test("a form with no field focuses its heading, not a button", async () => {
  const screen = await render(
    <Toolbar>
      <Folded title="Rotate the key" action="Rotate…">
        <button type="button">Rotate now</button>
      </Folded>
    </Toolbar>,
  );
  await screen.getByRole("button", { name: "Rotate…" }).click();
  await expect.element(screen.getByRole("heading", { name: "Rotate the key" })).toHaveFocus();
});

test("Escape from what the card opened elsewhere is that one's: the form stays open", async () => {
  const away = document.createElement("div");
  document.body.append(away);
  onTestFinished(() => away.remove());
  const screen = await render(
    <Toolbar>
      <Folded title="Find" action="Find…">
        <input aria-label="Thread" />
        {createPortal(<input aria-label="Popup" />, away)}
      </Folded>
    </Toolbar>,
  );
  await screen.getByRole("button", { name: "Find…" }).click();
  // Its key bubbles to the card through React's tree, though the popup is not inside the card.
  (away.querySelector("input") as HTMLInputElement).focus();
  await userEvent.keyboard("{Escape}");
  await expect.element(screen.getByRole("region", { name: "Find" })).toBeVisible();
  screen.getByRole("textbox", { name: "Thread" }).element().focus();
  await userEvent.keyboard("{Escape}");
  await expect.element(screen.getByRole("region", { name: "Find" })).not.toBeInTheDocument();
});

test("open forms are in their buttons' order, whichever opened first; with none open, the row beneath takes no room", async () => {
  const screen = await render(
    <Toolbar>
      <Folded title="Invite someone" action="Invite…">
        <input aria-label="Email" />
      </Folded>
      <Folded title="Add a member" action="Add…">
        <input aria-label="Who" />
      </Folded>
    </Toolbar>,
  );
  const invite = screen.getByRole("button", { name: "Invite…" });
  const beneath = invite.element().parentElement?.nextElementSibling?.firstElementChild as Element;
  expect(getComputedStyle(beneath).display).toBe("none");
  await screen.getByRole("button", { name: "Add…" }).click();
  await expect.element(screen.getByRole("region", { name: "Add a member" })).toBeVisible();
  expect(getComputedStyle(beneath).display).not.toBe("none");
  await invite.click();
  const first = screen.getByRole("region", { name: "Invite someone" }).element();
  const second = screen.getByRole("region", { name: "Add a member" }).element();
  expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});
