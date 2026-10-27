/**
 * A phone, with a finger as the pointer (portalr ADR-0082): the targets measured, not read from
 * the rules; the fields' text 16px; and what floats sitting as a sheet along the bottom, with a
 * dialog's manners, closed by Escape, by its backdrop, and by a drag down.
 */

import { useState } from "react";
import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Button } from "./button";
import { Dialog } from "./dialog";
import { Disclosure } from "./disclosure";
import { IconButton } from "./icon-button";
import { glyphs } from "./icons";
import { Menu } from "./menu";
import { Popover } from "./popover";
import { TextField } from "./text-field";

const height = (element: Element) => element.getBoundingClientRect().height;

test("to a finger, a button, an icon button, a field and a disclosure's line are 44px or taller", async () => {
  expect(matchMedia("(any-pointer: coarse)").matches).toBe(true);
  const screen = await render(
    <div className="flex flex-col gap-4 p-4">
      <Button>Approve</Button>
      <Button size="sm" variant="secondary">
        Small
      </Button>
      <IconButton label="Copy" icon={glyphs.copy} />
      <TextField label="Email" />
      <Disclosure summary="More">
        <p>Inside</p>
      </Disclosure>
    </div>,
  );
  for (const name of ["Approve", "Small", "Copy", "More"]) {
    expect(height(screen.getByRole("button", { name }).element()), name).toBeGreaterThanOrEqual(44);
  }
  const field = screen.getByRole("textbox", { name: "Email" }).element();
  expect(height(field)).toBeGreaterThanOrEqual(44);
  expect(Number.parseFloat(getComputedStyle(field).fontSize)).toBeGreaterThanOrEqual(16);
});

test("admin's compact rows reach 44px to a finger", async () => {
  const screen = await render(
    <div data-density="compact">
      <table>
        <tbody>
          <tr style={{ height: "var(--row-height)" }}>
            <td>alice</td>
          </tr>
        </tbody>
      </table>
    </div>,
  );
  expect(height(screen.getByRole("row").element())).toBeGreaterThanOrEqual(44);
});

function Opened({ onChange }: { onChange: (open: boolean) => void }) {
  return (
    <Dialog open onOpenChange={onChange} title="Share the thread" description="With whom.">
      <TextField label="Email" />
    </Dialog>
  );
}

test("a dialog is a sheet along the bottom: a dialog still, the focus in it, Escape and the backdrop closing it", async () => {
  const onChange = vi.fn();
  const screen = await render(<Opened onChange={onChange} />);
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  await expect.element(dialog).toBeVisible();
  await expect
    .poll(() => Math.round(dialog.element().getBoundingClientRect().bottom))
    .toBe(window.innerHeight);
  const box = dialog.element().getBoundingClientRect();
  const style = getComputedStyle(dialog.element());
  expect(style.position).toBe("fixed");
  expect(Math.round(box.left)).toBe(0);
  expect(Math.round(box.width)).toBe(window.innerWidth);
  expect(style.borderTopLeftRadius).not.toBe("0px");
  expect(style.borderBottomLeftRadius).toBe("0px");
  expect(dialog.element().querySelector("[data-sheet-handle]")).not.toBeNull();
  expect(
    getComputedStyle(dialog.element().querySelector("[data-sheet-handle]") as Element).display,
  ).toBe("block");
  await expect.element(screen.getByRole("textbox", { name: "Email" })).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  await expect.poll(() => onChange.mock.calls.at(-1)?.[0]).toBe(false);
});

test("a sheet dragged down past a third of its height closes; let go sooner, it stays", async () => {
  const onChange = vi.fn();
  const screen = await render(<Opened onChange={onChange} />);
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  const handle = () => dialog.element().querySelector("[data-sheet-handle]") as HTMLElement;
  // The touch module loads on first need.
  await expect.poll(() => dialog.element().onpointerdown !== undefined).toBe(true);
  await new Promise((settled) => setTimeout(settled, 300));
  const drag = (from: number, to: number) => {
    const down = new PointerEvent("pointerdown", {
      bubbles: true,
      clientY: from,
      pointerId: 1,
      pointerType: "touch",
    });
    handle().dispatchEvent(down);
    dialog.element().dispatchEvent(
      new PointerEvent("pointermove", {
        bubbles: true,
        clientY: to,
        pointerId: 1,
        pointerType: "touch",
      }),
    );
    dialog.element().dispatchEvent(
      new PointerEvent("pointerup", {
        bubbles: true,
        clientY: to,
        pointerId: 1,
        pointerType: "touch",
      }),
    );
  };
  drag(600, 620);
  expect(onChange).not.toHaveBeenCalled();
  const tall = dialog.element().getBoundingClientRect().height;
  drag(500, 500 + tall * 0.5);
  await expect.poll(() => onChange.mock.calls.length).toBe(1);
  expect(onChange.mock.calls.at(-1)?.[0]).toBe(false);
});

function Attach() {
  const [open, setOpen] = useState(false);
  return (
    <Popover
      label="Attach files"
      open={open}
      onOpenChange={setOpen}
      trigger={<Button variant="ghost">Attach</Button>}
    >
      <TextField label="File" />
    </Popover>
  );
}

test("a menu and a popover sit as sheets too, and keep their roles", async () => {
  const screen = await render(
    <div className="p-4">
      <Menu label="Thread actions" items={[{ label: "Share…", onSelect: vi.fn() }]} />
      <Attach />
    </div>,
  );
  const alongTheBottom = async (box: () => DOMRect) => {
    // It slides in from below (not here, where motion is reduced), then sits along the bottom.
    await expect.poll(() => Math.round(box().bottom)).toBe(window.innerHeight);
    expect(Math.round(box().width)).toBe(window.innerWidth);
  };
  await screen.getByRole("button", { name: "Thread actions" }).click();
  const menu = screen.getByRole("menu");
  await expect.element(menu).toBeVisible();
  await alongTheBottom(() => menu.element().getBoundingClientRect());
  await expect.element(menu.getByRole("menuitem", { name: "Share…" })).toBeVisible();
  await userEvent.keyboard("{Escape}");
  await expect.element(screen.getByRole("menu")).not.toBeInTheDocument();

  await screen.getByRole("button", { name: "Attach" }).click();
  const panel = screen.getByRole("dialog", { name: "Attach files" });
  await expect.element(panel).toBeVisible();
  await alongTheBottom(() => panel.element().getBoundingClientRect());
  await expect.element(screen.getByRole("textbox", { name: "File" })).toBeVisible();
  await userEvent.keyboard("{Escape}");
  await expect
    .element(screen.getByRole("dialog", { name: "Attach files" }))
    .not.toBeInTheDocument();
});
