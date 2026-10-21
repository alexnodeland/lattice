/**
 * Every element's computed look, snapshotted: the gate that lets the token layers move a component's
 * literals onto tokens and prove nothing changed (portalr ADR-0056). The galleries the screenshot
 * suites shoot are read at rest wide and narrow, under forced colours, and with motion allowed, and
 * each control is read hovered, focused from the keyboard, and held down. Only what a declaration
 * sets is read, so the snapshots are the same on every system: sizes, which layout decides for most
 * elements, are read by token-sizes.test.tsx and the screenshot suites; margins and transforms are
 * left out, as an automatic margin is read as the space it takes and a menu is placed by a
 * transform. A change to a component's look changes its snapshot, which a reviewer sees as text.
 */

import type { ReactNode } from "react";
import { afterEach, expect, onTestFinished, test } from "vitest";
import { commands, page, userEvent } from "vitest/browser";
import { cleanup, render } from "vitest-browser-react";
import { dark } from "./test/colours";
import {
  AdminGallery,
  Controls,
  Ended,
  Gallery,
  Kit,
  Rowed,
  Sharing,
  Sheet,
  Thread,
} from "./test/galleries";

/** What a declaration sets: colour, edges, corners, shadows, spacing, type and motion. */
const LOOK = [
  "color",
  "background-color",
  "background-image",
  ...["top", "right", "bottom", "left"].flatMap((side) => [
    `border-${side}-color`,
    `border-${side}-style`,
    `border-${side}-width`,
    `padding-${side}`,
  ]),
  "border-top-left-radius",
  "border-top-right-radius",
  "border-bottom-right-radius",
  "border-bottom-left-radius",
  "box-shadow",
  "outline-color",
  "outline-style",
  "outline-width",
  "outline-offset",
  "row-gap",
  "column-gap",
  "min-height",
  "max-width",
  "font-family",
  "font-size",
  "font-weight",
  "font-style",
  "line-height",
  "letter-spacing",
  "text-decoration-line",
  "text-decoration-color",
  "text-decoration-thickness",
  "text-underline-offset",
  "opacity",
  "scale",
  "translate",
  "filter",
  "backdrop-filter",
  "cursor",
  "accent-color",
  "fill",
  "stroke",
  "stroke-width",
] as const;

/** How a thing moves: read with motion allowed, as reduced motion stops it. */
const MOTION = [
  "transition-property",
  "transition-duration",
  "transition-timing-function",
  "transition-delay",
  "animation-name",
  "animation-duration",
  "animation-timing-function",
  "animation-iteration-count",
  "animation-play-state",
] as const;

/** What an element inherits unless it sets its own: written only where it differs from its parent's. */
const INHERITED = new Set<string>([
  "color",
  "font-family",
  "font-size",
  "font-weight",
  "font-style",
  "line-height",
  "letter-spacing",
  "cursor",
  "fill",
  "stroke",
  "stroke-width",
  "accent-color",
]);

/** Each property's value as nothing set it, so a line says only what is set. */
const UNSET: Record<string, readonly string[]> = {
  "background-color": ["rgba(0, 0, 0, 0)"],
  "background-image": ["none"],
  "border-top-style": ["none"],
  "border-right-style": ["none"],
  "border-bottom-style": ["none"],
  "border-left-style": ["none"],
  "box-shadow": ["none"],
  "outline-style": ["none"],
  "outline-offset": ["0px"],
  opacity: ["1"],
  scale: ["none"],
  translate: ["none"],
  filter: ["none"],
  "backdrop-filter": ["none"],
  "min-height": ["auto", "0px"],
  "max-width": ["none"],
  "row-gap": ["normal"],
  "column-gap": ["normal"],
  "text-decoration-line": ["none"],
  "transition-property": ["all"],
  "transition-duration": ["0s"],
  "transition-timing-function": ["ease"],
  "transition-delay": ["0s"],
  "animation-name": ["none"],
  "animation-duration": ["0s"],
  "animation-timing-function": ["ease"],
  "animation-iteration-count": ["1"],
  "animation-play-state": ["running"],
};

/** A border's colour and width say nothing where it has no style, and an outline's likewise. */
function said(style: CSSStyleDeclaration, property: string, value: string) {
  if ((UNSET[property] ?? []).includes(value)) return false;
  for (const side of ["top", "right", "bottom", "left"]) {
    if (property === `border-${side}-color` || property === `border-${side}-width`) {
      return style.getPropertyValue(`border-${side}-style`) !== "none";
    }
  }
  if (property === "outline-color" || property === "outline-width") {
    return style.outlineStyle !== "none";
  }
  if (property.startsWith("transition-") && property !== "transition-property") {
    return style.transitionDuration !== "0s" || style.transitionProperty !== "all";
  }
  if (property.startsWith("animation-") && property !== "animation-name") {
    return style.animationName !== "none";
  }
  if (property.startsWith("padding-") || property === "text-underline-offset") {
    return value !== "0px" && value !== "auto";
  }
  if (property.startsWith("text-decoration-") && property !== "text-decoration-line") {
    return style.textDecorationLine !== "none";
  }
  return true;
}

/** Where an element sits: its tag and its place among its siblings, from the body down. */
function pathOf(element: Element) {
  const steps: string[] = [];
  for (let at: Element | null = element; at && at !== document.body; at = at.parentElement) {
    const index = at.parentElement ? [...at.parentElement.children].indexOf(at) : 0;
    steps.unshift(`${at.tagName.toLowerCase()}${index}`);
  }
  return steps.join(">");
}

/** An element's line: its place, then what its look sets, if anything. */
function entry(place: string, set: readonly string[]) {
  return set.length > 0 ? `${place} | ${set.join("; ")}` : place;
}

/** A snapshot's text: its readings' lines, none of them empty, and a newline at its end. */
function file(readings: readonly string[]) {
  return `${readings.join("\n").split("\n").filter(Boolean).join("\n")}\n`;
}

/**
 * The colours the system chooses, which differ from one system to the next: the browser's own
 * focus ring always, and, under forced colours, where every colour is the system's, each system
 * colour. Each is written by its name, so a snapshot is the same on every system.
 */
const SYSTEM = [
  "Canvas",
  "CanvasText",
  "LinkText",
  "VisitedText",
  "ActiveText",
  "ButtonFace",
  "ButtonText",
  "ButtonBorder",
  "Field",
  "FieldText",
  "Highlight",
  "HighlightText",
  "SelectedItem",
  "SelectedItemText",
  "Mark",
  "MarkText",
  "GrayText",
  "AccentColor",
  "AccentColorText",
] as const;

function systemColours(forced: boolean) {
  const probe = document.createElement("span");
  document.body.append(probe);
  const named = new Map<string, string>();
  for (const name of forced ? SYSTEM : []) {
    probe.style.color = name;
    const value = getComputedStyle(probe).color;
    if (!named.has(value)) named.set(value, name);
  }
  probe.style.outlineColor = "-webkit-focus-ring-color";
  const ring = getComputedStyle(probe).outlineColor;
  if (!named.has(ring)) named.set(ring, "FocusRing");
  probe.remove();
  return named;
}

/** `value` with each colour the system chose written by its name. */
function named(value: string, system: ReadonlyMap<string, string>) {
  return value.replace(/(?:rgba?|color)\([^)]*\)/g, (colour) => system.get(colour) ?? colour);
}

/** One line per element in `root` and below: its place, and what its look sets. */
function read(root: Element, properties: readonly string[]) {
  const system = systemColours(matchMedia("(forced-colors: active)").matches);
  const lines: string[] = [];
  for (const element of [root, ...root.querySelectorAll("*")]) {
    if (element.closest("script, style, template")) continue;
    const style = getComputedStyle(element);
    const parent = element.parentElement ? getComputedStyle(element.parentElement) : null;
    const set = properties.flatMap((property) => {
      const value = style.getPropertyValue(property);
      if (INHERITED.has(property) && parent?.getPropertyValue(property) === value) return [];
      return said(style, property, value) ? [`${property}: ${named(value, system)}`] : [];
    });
    lines.push(entry(pathOf(element), set));
    for (const pseudo of ["::before", "::after", "::placeholder", "::marker"] as const) {
      const of = getComputedStyle(element, pseudo);
      if (pseudo.endsWith("before") || pseudo.endsWith("after")) {
        if (of.content === "none" || of.content === "normal") continue;
      } else if (
        pseudo === "::placeholder" &&
        !(element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement)
      ) {
        continue;
      } else if (pseudo === "::marker" && style.display !== "list-item") {
        continue;
      }
      const values = properties
        .map((property) => [property, of.getPropertyValue(property)] as const)
        .filter(([property, value]) => said(of, property, value))
        .map(([property, value]) => `${property}: ${named(value, system)}`);
      lines.push(entry(`${pathOf(element)}${pseudo}`, values));
    }
  }
  return lines.join("\n");
}

/** The lines of `reading` that `against` doesn't have: what a width or a mode changes. */
function unlike(reading: string, against: string) {
  const seen = new Set(against.split("\n"));
  return reading
    .split("\n")
    .filter((line) => !seen.has(line))
    .join("\n");
}

/** Two frames: what a state sets has been applied, and what it starts has started. */
const frames = () =>
  new Promise((settled) => requestAnimationFrame(() => requestAnimationFrame(settled)));

const scheme = dark ? "dark" : "light";

/** The scenes, each as the screenshot suites lay it out, with a dialog's or a menu's portal in the body. */
const SCENES: Record<string, () => ReactNode> = {
  gallery: () => <Gallery />,
  admin: () => <AdminGallery />,
  dialog: () => (
    <>
      <Gallery />
      <Sharing />
    </>
  ),
  controls: () => <Controls />,
  thread: () => <Thread />,
  ended: () => <Ended />,
  sheet: () => <Sheet />,
  "rowed-app": () => <Rowed ui="app" />,
  "rowed-admin": () => <Rowed ui="admin" />,
  kit: () => <Kit />,
  menu: () => <Gallery />,
  select: () => <Controls />,
  drawer: () => <Gallery />,
  tooltip: () => <Kit />,
};

/** What a scene opens once it is shown: a menu, with the keyboard on an item, or a select's list. */
const OPENED: Record<string, () => Promise<void>> = {
  menu: async () => {
    await page.getByRole("button", { name: "Workspace: acme, notes" }).click();
    await userEvent.keyboard("{ArrowDown}");
  },
  // An icon button's tooltip, shown as the pointer rests on it.
  tooltip: async () => {
    await userEvent.hover(page.getByRole("button", { name: "Full view" }));
    await expect.element(page.getByText("Full view", { exact: true })).toBeVisible();
  },
  // The drawer opens where the frame is narrow, and isn't there to open where it is wide.
  drawer: async () => {
    const menu = page.getByRole("button", { name: "Menu" });
    if (menu.query()?.checkVisibility()) {
      await menu.click();
      await expect.element(page.getByRole("dialog", { name: "Navigation" })).toBeVisible();
    }
  },
  select: async () => {
    await page.getByRole("combobox", { name: "Role" }).click();
    await expect.element(page.getByRole("listbox")).toBeVisible();
  },
};

/** What a person can point at, press or reach with the keyboard. */
const CONTROLS =
  "a[href], button, input, textarea, select, summary, [role='combobox'], [role='switch'], [role='checkbox'], [role='radio'], [role='tab'], [tabindex='0']";

/** The media the test has asked the browser for: forced colours, and reduced motion (the default). */
const asked = { forced: false, reduced: true };

async function forcedColors(active: boolean) {
  asked.forced = active;
  await commands.forcedColors(active);
}

async function reduceMotion(reduce: boolean) {
  asked.reduced = reduce;
  await commands.reduceMotion(reduce);
}

async function shown(scene: string, width: number) {
  await page.viewport(width, 900);
  onTestFinished(() => page.viewport(414, 896));
  // The page's media are what the test asked for before anything is read: the browser applies an
  // emulated media change a moment after it is asked for.
  await expect.poll(() => matchMedia("(forced-colors: active)").matches).toBe(asked.forced);
  await expect
    .poll(() => matchMedia("(prefers-reduced-motion: reduce)").matches)
    .toBe(asked.reduced);
  const screen = await render(SCENES[scene]?.());
  await OPENED[scene]?.();
  // An opened list or menu is read once it has finished opening, not while it enters.
  await expect
    .poll(() => document.querySelector("[data-starting-style], [data-ending-style]"))
    .toBeNull();
  // The pointer moves off what a scene shows, but where it rests to show a tooltip.
  if (scene !== "tooltip") await commands.pointerAway();
  await frames();
  return screen;
}

afterEach(async () => {
  // Whatever a test left, so the next starts on an empty page with the button up.
  cleanup();
  await commands.pointAt("");
  await forcedColors(false);
  await reduceMotion(true);
});

for (const scene of Object.keys(SCENES)) {
  test(`${scene}: at rest, wide and narrow, under forced colours, and moving`, async () => {
    await shown(scene, 1280);
    const wide = read(document.body, LOOK);
    cleanup();
    await shown(scene, 390);
    const narrow = read(document.body, LOOK);
    cleanup();
    await forcedColors(true);
    await shown(scene, 1280);
    const forced = read(document.body, LOOK);
    cleanup();
    await forcedColors(false);
    await reduceMotion(false);
    await shown(scene, 1280);
    const moving = read(document.body, MOTION);
    await expect(
      file([
        "# wide",
        wide,
        "# narrow",
        unlike(narrow, wide),
        "# forced colours",
        unlike(forced, wide),
        "# moving",
        moving,
      ]),
    ).toMatchFileSnapshot(`./__computed__/${scene}.rest.${scheme}.txt`);
  }, 60_000);

  // An open menu or list holds the page's focus and pointer, so its scene is read at rest alone.
  test.skipIf(scene in OPENED)(
    `${scene}: each control hovered, focused from the keyboard, and held down`,
    async () => {
      await shown(scene, 1280);
      const count = document.body.querySelectorAll(CONTROLS).length;
      // A state's lines are those it changes from the scene at rest.
      const rest = read(document.body, LOOK);
      cleanup();
      const states: string[] = [];
      for (let at = 0; at < count; at++) {
        for (const state of ["hover", "focus-visible", "active"] as const) {
          await shown(scene, 1280);
          const control = document.body.querySelectorAll(CONTROLS)[at];
          if (!(control instanceof HTMLElement) || control.getClientRects().length === 0) {
            cleanup();
            continue;
          }
          control.dataset.probe = "";
          if (state === "hover") await commands.pointAt("[data-probe]");
          if (state === "focus-visible") {
            await userEvent.keyboard("{Shift}");
            control.focus();
          }
          if (state === "active") await commands.pointAt("[data-probe]", true);
          delete control.dataset.probe;
          await frames();
          states.push(`# ${pathOf(control)} ${state}`, unlike(read(control, LOOK), rest));
          if (state === "active") await commands.pointAt("");
          cleanup();
        }
      }
      await expect(file(states)).toMatchFileSnapshot(
        `./__computed__/${scene}.states.${scheme}.txt`,
      );
    },
    // A scene is shown again for each control in each state: a minute or two on a slow runner.
    240_000,
  );
}
