/**
 * Reduced motion is structural (portalr ADR-0057): whatever a kit's durations, where a person asks
 * for less motion nothing moves. The worst kit the guard rails allow is the generated tokens.css
 * with every duration at 600ms, in the form the generator writes it; laid over the default, every
 * element of the galleries, with a dialog, a menu, a select's list and the drawer open, then has no
 * transition that takes time and no animation that runs.
 */

import type { CSSProperties, ReactNode } from "react";
import { afterEach, expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { cleanup, render } from "vitest-browser-react";
import { Dialog } from "./dialog";
import { Controls, Gallery, Kit, Sheet, Thread } from "./test/galleries";
import tokens from "./tokens.css?raw";

/** A duration token's declaration, but the placeholder's loop, which reduced motion pauses. */
const DURATION = /^(\s*--(?!duration-(?:pulse|spin))[\w-]*duration[\w-]*): .*;$/gm;

/**
 * The generated stylesheet with every duration, a primitive's or a component's, at the rails'
 * 600ms, written as the generator writes a duration a kit sets: the worst kit.
 */
function worstKit() {
  expect(tokens.match(DURATION)?.length ?? 0).toBeGreaterThanOrEqual(8);
  const style = document.createElement("style");
  style.textContent = tokens.replace(DURATION, "$1: calc(600ms * var(--motion-scale));");
  document.head.append(style);
  return style;
}

/** Each element that would move: a transition that takes time, or an animation that runs. */
function moving() {
  return [...document.body.querySelectorAll("*")].flatMap((element) => {
    const style = getComputedStyle(element);
    const still =
      style.transitionProperty === "none" ||
      style.transitionDuration.split(", ").every((duration) => duration === "0s");
    const playing = style.animationName !== "none" && style.animationPlayState !== "paused";
    return still && !playing ? [] : [element.outerHTML.slice(0, 120)];
  });
}

afterEach(async () => {
  cleanup();
  await commands.reduceMotion(true);
});

const SCENES: [string, ReactNode, (() => Promise<void>) | null][] = [
  ["the frame", <Gallery key="gallery" />, null],
  [
    "the frame with a menu open",
    <Gallery key="menu" />,
    () => page.getByRole("button", { name: "Workspace: acme, notes" }).click(),
  ],
  [
    "the drawer open",
    <Gallery key="drawer" />,
    async () => {
      await page.viewport(390, 900);
      await page.getByRole("button", { name: "Menu" }).click();
    },
  ],
  [
    "a dialog open",
    <Dialog key="dialog" open onOpenChange={() => undefined} title="Share">
      Who holds a role on it.
    </Dialog>,
    null,
  ],
  [
    "a select's list open",
    <Controls key="select" />,
    () => page.getByRole("combobox", { name: "Role" }).click(),
  ],
  ["the kit", <Kit key="kit" />, null],
  ["a thread", <Thread key="thread" />, null],
  ["the statuses", <Sheet key="sheet" />, null],
];

test.each(SCENES)(
  "under reduced motion, %s neither moves nor animates, whatever the kit",
  async (_, scene, open) => {
    onTestFinished(() => page.viewport(414, 896));
    await commands.reduceMotion(true);
    const kit = worstKit();
    try {
      await render(scene);
      await open?.();
      expect(moving()).toEqual([]);
    } finally {
      kit.remove();
    }
  },
);

test("with motion allowed, the same kit's transitions take their time", async () => {
  await commands.reduceMotion(false);
  const kit = worstKit();
  try {
    await render(<Controls />);
    const durations = [...document.body.querySelectorAll("*")].map(
      (element) => getComputedStyle(element).transitionDuration,
    );
    expect(durations).toContain("0.6s");
  } finally {
    kit.remove();
  }
});

test("no kit declares motion's scale or loop: they are base.css's, and no token's", () => {
  expect(tokens).not.toMatch(/--motion-(?:scale|loop)\s*:/);
});

/**
 * Not even an element that declares motion's scale itself undoes it: every duration token is
 * declared on the root, where motion's scale is already 0, so what an element inherits is a
 * duration of 0, whatever it declares below. Nothing a kit writes can declare it anyway, as the
 * test above holds.
 */
test("an element that declares motion's scale itself still doesn't move", async () => {
  await commands.reduceMotion(true);
  const kit = worstKit();
  try {
    await render(
      <div style={{ "--motion-scale": "1" } as CSSProperties}>
        <span className="transition-colors">still</span>
        <Controls />
      </div>,
    );
    expect(moving()).toEqual([]);
  } finally {
    kit.remove();
  }
});
