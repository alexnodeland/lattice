import { expect, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Card } from "./card";
import { Dialog } from "./dialog";
import { glyphs } from "./icons";
import { Menu } from "./menu";
import { RailShell } from "./rail-shell";

/** A box-shadow's alpha, and whether its colour is black, from the computed value in either colour syntax. */
function shadowOf(element: Element) {
  const value = getComputedStyle(element).boxShadow;
  // Tailwind lays transparent ring and inset layers first: the shadow itself is the last colour.
  const colours = [
    ...value.matchAll(
      /(?:rgba?\(|color\(srgb )([\d.]+)[, ]+([\d.]+)[, ]+([\d.]+)(?:[,/ ]+([\d.]+))?\)/g,
    ),
  ];
  const [, a = "", b = "", c = "", alpha = "1"] = colours.at(-1) ?? [];
  return { alpha: Number(alpha), black: Number(a) + Number(b) + Number(c) === 0 };
}

test("a card casts a faint shadow, and a menu casts more", async () => {
  const screen = await render(
    <>
      <Card>A card</Card>
      <Menu
        label="Actions"
        icon={glyphs.more}
        items={[{ label: "Open", onSelect: () => undefined }]}
      />
    </>,
  );
  const card = screen.getByText("A card").element();
  expect(getComputedStyle(card).boxShadow).not.toBe("none");
  await screen.getByRole("button", { name: "Actions" }).click();
  const menu = page.getByRole("menu").element();
  expect(getComputedStyle(menu).boxShadow).not.toBe("none");
  expect(shadowOf(menu).alpha).toBeGreaterThanOrEqual(shadowOf(card).alpha);
  // The menu's is the longer shadow: it floats higher than a card sits.
  expect(getComputedStyle(menu).boxShadow.length).toBeGreaterThan(
    getComputedStyle(card).boxShadow.length,
  );
});

test("a dialog casts the most shadow, over a scrim that blurs what is behind it", async () => {
  await render(
    <Dialog open onOpenChange={() => undefined} title="Share the thread">
      Who holds a role on it.
    </Dialog>,
  );
  const dialog = page.getByRole("dialog", { name: "Share the thread" }).element();
  expect(getComputedStyle(dialog).boxShadow).not.toBe("none");
  const backdrop = document.querySelector("[class*='bg-scrim']");
  expect(getComputedStyle(backdrop as Element).backdropFilter).toMatch(/blur\(/);
});

test("the shadow is a whisper of a neutral in light, and black and heavier in dark, where a faint one would not be seen (portalr ADR-0079)", async () => {
  const screen = await render(<Card>A card</Card>);
  const card = screen.getByText("A card").element();
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  const { alpha, black } = shadowOf(card);
  expect(black).toBe(dark);
  expect(alpha).toBeGreaterThan(dark ? 0.5 : 0.05);
  expect(alpha).toBeLessThan(dark ? 0.7 : 0.1);
});

test("a drawer casts its shadow too", async () => {
  const screen = await render(
    <RailShell
      home={<a href="#home" />}
      switcher={<span>switcher</span>}
      account={<span>account</span>}
      nav={<nav>nav</nav>}
    >
      page
    </RailShell>,
  );
  await page.viewport(390, 800);
  await screen.getByRole("button", { name: "Menu" }).click();
  const drawer = page.getByRole("dialog", { name: "Navigation" }).element();
  expect(getComputedStyle(drawer).boxShadow).not.toBe("none");
});

test("a dialog opens with a fade and a scale, and with none where motion is reduced", async () => {
  const screen = await render(
    <Dialog open onOpenChange={() => undefined} title="Share the thread">
      Who holds a role on it.
    </Dialog>,
  );
  const dialog = screen.getByRole("dialog", { name: "Share the thread" }).element();
  expect(getComputedStyle(dialog).transitionProperty).toBe("none");
  await commands.reduceMotion(false);
  try {
    await expect.poll(() => getComputedStyle(dialog).transitionProperty).toMatch(/opacity/);
    expect(getComputedStyle(dialog).transitionDuration).not.toBe("0s");
  } finally {
    await commands.reduceMotion(true);
  }
});
