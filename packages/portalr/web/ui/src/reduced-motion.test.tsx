/**
 * Reduced motion is structural (portalr ADR-0057): whatever a kit's durations, where a person asks
 * for less motion nothing moves. A kit at the guard rails' worst, every duration 600ms as the
 * generated stylesheet would scale it, is laid over the default; every element of the galleries
 * then has no transition that takes time, and no animation that runs.
 */

import { afterEach, expect, test } from "vitest";
import { commands } from "vitest/browser";
import { cleanup, render } from "vitest-browser-react";
import { Controls, Gallery, Kit, Sheet, Thread } from "./test/galleries";

/** Every duration the stylesheet declares, at the rails' 600ms, scaled as a kit's would be. */
function worstKit() {
  const durations = [...document.styleSheets]
    .flatMap((sheet) => [...sheet.cssRules])
    .filter((rule): rule is CSSStyleRule => rule instanceof CSSStyleRule)
    .flatMap((rule) => [...rule.style].filter((name) => /^--[\w-]*duration[\w-]*$/.test(name)));
  const style = document.createElement("style");
  style.textContent = `:root { ${[...new Set(durations)]
    .filter((name) => name !== "--duration-pulse")
    .map((name) => `${name}: calc(600ms * var(--motion-scale));`)
    .join(" ")} }`;
  document.head.append(style);
  return style;
}

afterEach(async () => {
  cleanup();
  await commands.reduceMotion(true);
});

test.each([
  ["the frame", <Gallery key="gallery" />],
  ["the controls", <Controls key="controls" />],
  ["the kit", <Kit key="kit" />],
  ["a thread", <Thread key="thread" />],
  ["the statuses", <Sheet key="sheet" />],
])("under reduced motion, %s neither moves nor animates, whatever the kit", async (_, scene) => {
  await commands.reduceMotion(true);
  const kit = worstKit();
  try {
    await render(scene);
    const moving = [...document.body.querySelectorAll("*")].flatMap((element) => {
      const style = getComputedStyle(element);
      const durations = style.transitionDuration.split(", ");
      const still =
        style.transitionProperty === "none" || durations.every((duration) => duration === "0s");
      const playing = style.animationName !== "none" && style.animationPlayState !== "paused";
      return still && !playing ? [] : [element.outerHTML.slice(0, 120)];
    });
    expect(moving).toEqual([]);
  } finally {
    kit.remove();
  }
});

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
