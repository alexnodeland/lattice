/**
 * What the computed-style snapshots don't read (portalr ADR-0056): the size tokens that set a box's
 * width or height, the dialog's width and margin, the drawer's width, the switch, the check, the
 * progress bar and a row, each read where it is used, so a misspelt one fails here; and the scale a
 * dialog or a menu enters and leaves at, which lasts a frame. Corners and padding are read by the
 * computed-style snapshots; the screenshot suites guard every other size.
 */

import { expect, onTestFinished, test } from "vitest";
import { page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { AppShell } from "./app-shell";
import { Checkbox } from "./checkbox";
import { Dialog } from "./dialog";
import { glyphs } from "./icons";
import { Menu } from "./menu";
import { Progress } from "./progress";
import { Switch } from "./switch";
import { Table } from "./table";

const box = (element: Element) => element.getBoundingClientRect();

test("a dialog is the dialog's width, and enters and leaves at its scale", async () => {
  await page.viewport(1280, 900);
  onTestFinished(() => page.viewport(414, 896));
  await render(
    <Dialog open onOpenChange={() => undefined} title="Share">
      Who holds a role on it.
    </Dialog>,
  );
  const dialog = page.getByRole("dialog", { name: "Share" }).element();
  expect(box(dialog).width).toBe(512);
  dialog.setAttribute("data-starting-style", "");
  expect(getComputedStyle(dialog).scale).toBe("0.98");
  dialog.removeAttribute("data-starting-style");
  dialog.setAttribute("data-ending-style", "");
  expect(getComputedStyle(dialog).scale).toBe("0.98");
});

test("a dialog keeps its margin from a narrow window's edges", async () => {
  await page.viewport(390, 900);
  onTestFinished(() => page.viewport(414, 896));
  await render(
    <Dialog open onOpenChange={() => undefined} title="Share">
      Who holds a role on it.
    </Dialog>,
  );
  expect(box(page.getByRole("dialog", { name: "Share" }).element()).width).toBe(390 - 32);
});

test("a menu enters and leaves at the popover's scale", async () => {
  const screen = await render(
    <Menu
      label="Actions"
      icon={glyphs.more}
      items={[{ label: "Open", onSelect: () => undefined }]}
    />,
  );
  await screen.getByRole("button", { name: "Actions" }).click();
  await expect.element(page.getByRole("menu")).toBeVisible();
  const menu = page.getByRole("menu").element();
  menu.setAttribute("data-starting-style", "");
  expect(getComputedStyle(menu).scale).toBe("0.98");
});

test("the drawer is the drawer's width", async () => {
  await page.viewport(390, 900);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(
    <AppShell home={<a href="#home" />} switcher={<span>acme</span>} account={<span>alice</span>}>
      Content
    </AppShell>,
  );
  await screen.getByRole("button", { name: "Menu" }).click();
  // 19rem, or 85% of a window narrower than it.
  expect(box(page.getByRole("dialog", { name: "Navigation" }).element()).width).toBe(304);
});

test("a switch, its thumb, a check and a progress bar are their tokens' sizes", async () => {
  const screen = await render(
    <>
      <Switch aria-label="On" defaultChecked />
      <Checkbox aria-label="Done" />
      <Progress label="Checking in" value={1} max={2} />
    </>,
  );
  const control = screen.getByRole("switch", { name: "On" }).element();
  expect([box(control).width, box(control).height]).toEqual([36, 20]);
  const thumb = control.firstElementChild as Element;
  expect([box(thumb).width, box(thumb).height]).toEqual([16, 16]);
  // On, the thumb has travelled its 16px: from inside the edge and padding to the edge itself.
  expect(box(thumb).right).toBe(box(control).right - 1);
  const check = screen.getByRole("checkbox", { name: "Done" }).element();
  expect([box(check).width, box(check).height]).toEqual([16, 16]);
  const bar = screen.getByRole("progressbar").element();
  expect(box(bar).height).toBe(8);
});

test("a table's row is the row's height", async () => {
  const screen = await render(
    <Table caption="Members">
      <tbody>
        <tr>
          <td>alice</td>
        </tr>
      </tbody>
    </Table>,
  );
  expect(box(screen.getByRole("row").element()).height).toBe(48);
});
