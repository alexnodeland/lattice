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

test("Ctrl+K and ⌘K open the palette, in a field too", () => {
  expect(opensPalette(key({ key: "k", ctrlKey: true }))).toBe(true);
  expect(opensPalette(key({ key: "K", metaKey: true }))).toBe(true);
  expect(opensPalette(key({ key: "k", metaKey: true }, document.createElement("textarea")))).toBe(
    true,
  );
  expect(opensPalette(key({ key: "k" }))).toBe(false);
  expect(opensPalette(key({ key: "k", ctrlKey: true, shiftKey: true }))).toBe(false);
});

test('"/" opens it outside a field, and never with Ctrl, ⌘ or Alt held', () => {
  expect(opensPalette(key({ key: "/" }))).toBe(true);
  expect(opensPalette(key({ key: "/" }, document.createElement("input")))).toBe(false);
  for (const held of ["ctrlKey", "metaKey", "altKey"]) {
    expect(opensPalette(key({ key: "/", [held]: true }))).toBe(false);
  }
});

test("no key opens it over a dialog already open", () => {
  const dialog = document.createElement("div");
  dialog.setAttribute("role", "dialog");
  document.body.append(dialog);
  expect(opensPalette(key({ key: "/" }))).toBe(false);
  expect(opensPalette(key({ key: "k", ctrlKey: true }))).toBe(false);
});
