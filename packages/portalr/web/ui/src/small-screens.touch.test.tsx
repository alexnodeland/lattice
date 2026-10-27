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
import { ComposerDock } from "./composer-dock";
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
  // The handle shows once the drag listens, which the touch module's arrival turns on.
  await expect.poll(() => dialog.element().hasAttribute("data-sheet-drag")).toBe(true);
  const handle = dialog.element().querySelector("[data-sheet-handle]") as HTMLElement;
  expect(getComputedStyle(handle).display).toBe("block");
  expect(handle.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
  await expect.element(screen.getByRole("textbox", { name: "Email" })).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  await expect.poll(() => onChange.mock.calls.at(-1)?.[0]).toBe(false);
});

test("a sheet dragged down past a third of its height closes; let go sooner, it stays", async () => {
  const onChange = vi.fn();
  const screen = await render(<Opened onChange={onChange} />);
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  const handle = () => dialog.element().querySelector("[data-sheet-handle]") as HTMLElement;
  // The touch module loads as the sheet opens; the drag listens once it is here.
  await expect.poll(() => dialog.element().hasAttribute("data-sheet-drag")).toBe(true);
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

const pe = (type: string, y: number, extra: PointerEventInit = {}) =>
  new PointerEvent(type, {
    bubbles: true,
    clientY: y,
    pointerId: 1,
    pointerType: "touch",
    ...extra,
  });
const settle = (ms = 100) => new Promise((r) => setTimeout(r, ms));
const armed = (el: Element) =>
  expect.poll(() => el.hasAttribute("data-sheet-drag"), { timeout: 3000 }).toBe(true);

function Closed({ onChange }: { onChange: (open: boolean) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Share</Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          onChange(next);
        }}
        title="Share the thread"
      >
        <TextField label="Email" />
      </Dialog>
    </>
  );
}

test("a dialog opened by its button is dragged closed too: the drag arms as the popup mounts", async () => {
  const onChange = vi.fn();
  const screen = await render(<Closed onChange={onChange} />);
  await settle(800);
  await screen.getByRole("button", { name: "Share" }).click();
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  await expect.element(dialog).toBeVisible();
  const el = dialog.element() as HTMLElement;
  await armed(el);
  const handle = el.querySelector("[data-sheet-handle]") as HTMLElement;
  handle.dispatchEvent(pe("pointerdown", 500));
  el.dispatchEvent(pe("pointermove", 500 + el.offsetHeight * 0.6));
  el.dispatchEvent(pe("pointerup", 500 + el.offsetHeight * 0.6));
  await expect.poll(() => onChange.mock.calls.at(-1)?.[0], { timeout: 1500 }).toBe(false);
});

test("the sheet follows the finger while dragged", async () => {
  const screen = await render(
    <Dialog open onOpenChange={vi.fn()} title="Share the thread">
      <TextField label="Email" />
    </Dialog>,
  );
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  await expect.element(dialog).toBeVisible();
  const el = dialog.element() as HTMLElement;
  await armed(el);
  const rest = el.getBoundingClientRect().top;
  (el.querySelector("[data-sheet-handle]") as HTMLElement).dispatchEvent(pe("pointerdown", 500));
  el.dispatchEvent(pe("pointermove", 560));
  expect(Math.round(el.getBoundingClientRect().top - rest)).toBe(60);
  el.dispatchEvent(pe("pointerup", 560));
});

test("a gesture the browser takes springs the sheet back, never closes it", async () => {
  const onChange = vi.fn();
  const screen = await render(
    <Dialog open onOpenChange={onChange} title="Share the thread">
      <TextField label="Email" />
    </Dialog>,
  );
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  await expect.element(dialog).toBeVisible();
  const el = dialog.element() as HTMLElement;
  await armed(el);
  const rest = el.getBoundingClientRect().top;
  (el.querySelector("[data-sheet-handle]") as HTMLElement).dispatchEvent(pe("pointerdown", 500));
  el.dispatchEvent(pe("pointermove", 500 + el.offsetHeight * 0.6));
  el.dispatchEvent(pe("pointercancel", 500 + el.offsetHeight * 0.6));
  await settle(100);
  expect(onChange).not.toHaveBeenCalled();
  expect(Math.round(el.getBoundingClientRect().top)).toBe(Math.round(rest));
});

test("a pinch zoom is no keyboard: nothing is kept clear for it", async () => {
  const real = window.visualViewport;
  const viewport = new EventTarget() as EventTarget & {
    height: number;
    offsetTop: number;
    scale: number;
  };
  viewport.height = window.innerHeight / 2;
  viewport.offsetTop = 0;
  viewport.scale = 2;
  Object.defineProperty(window, "visualViewport", { value: viewport, configurable: true });
  try {
    await render(
      <ComposerDock>
        <button type="submit">Send</button>
      </ComposerDock>,
    );
    await settle();
    expect(document.documentElement.style.getPropertyValue("--keyboard-inset")).toBe("0px");
  } finally {
    Object.defineProperty(window, "visualViewport", { value: real, configurable: true });
  }
});

test("a flick down closes the sheet though it went a short way", async () => {
  const onChange = vi.fn();
  const screen = await render(<Opened onChange={onChange} />);
  const dialog = screen.getByRole("dialog", { name: "Share the thread" });
  await expect.element(dialog).toBeVisible();
  const el = dialog.element() as HTMLElement;
  await armed(el);
  const handle = el.querySelector("[data-sheet-handle]") as HTMLElement;
  handle.dispatchEvent(pe("pointerdown", 500));
  // 40px in about 20ms: a flick, well short of a third of the sheet.
  await settle(20);
  el.dispatchEvent(pe("pointermove", 540));
  el.dispatchEvent(pe("pointerup", 540));
  await expect.poll(() => onChange.mock.calls.at(-1)?.[0]).toBe(false);
});
