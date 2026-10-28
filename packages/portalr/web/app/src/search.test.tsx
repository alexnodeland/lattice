import { afterEach, expect, test } from "vitest";
import { opensPalette } from "./search";

const key = (init: KeyboardEventInit, target?: Element) => {
  const event = new KeyboardEvent("keydown", init);
  if (target) {
    Object.defineProperty(event, "target", { value: target });
  }
  return event;
};

afterEach(() => {
  document.body.replaceChildren();
});

test("⌘K opens the palette anywhere, a field too; Ctrl+K outside a field, and in one but on a Mac", () => {
  const field = document.createElement("textarea");
  for (const mac of [true, false]) {
    expect(opensPalette(key({ key: "K", metaKey: true }), mac)).toBe(true);
    expect(opensPalette(key({ key: "k", metaKey: true }, field), mac)).toBe(true);
    expect(opensPalette(key({ key: "k", ctrlKey: true }), mac)).toBe(true);
    expect(opensPalette(key({ key: "k" }), mac)).toBe(false);
    expect(opensPalette(key({ key: "k", ctrlKey: true, shiftKey: true }), mac)).toBe(false);
  }
  // On a Mac, Ctrl+K in a field kills to the line's end: the field keeps it.
  expect(opensPalette(key({ key: "k", ctrlKey: true }, field), true)).toBe(false);
  expect(opensPalette(key({ key: "k", ctrlKey: true }, field), false)).toBe(true);
});

test('"/" opens it outside a field, and never with Ctrl, ⌘ or Alt held', () => {
  expect(opensPalette(key({ key: "/" }))).toBe(true);
  expect(opensPalette(key({ key: "/" }, document.createElement("input")))).toBe(false);
  for (const held of ["ctrlKey", "metaKey", "altKey"]) {
    expect(opensPalette(key({ key: "/", [held]: true }))).toBe(false);
  }
});

for (const role of ["dialog", "alertdialog", "menu"]) {
  test(`no key opens it over a ${role} already open`, () => {
    const open = document.createElement("div");
    open.setAttribute("role", role);
    document.body.append(open);
    expect(opensPalette(key({ key: "/" }))).toBe(false);
    expect(opensPalette(key({ key: "k", metaKey: true }))).toBe(false);
  });
}
