import { markdown } from "@portalr/ui";
import { expect, test } from "vitest";
import { titleOf, titlesOf } from "./titles";

const renderers = new Map([["note", markdown()]]);

test("a title is the kind's renderer's, and null for data it can't read", () => {
  expect(titleOf("note", { text: "# Launch plan\nbody" }, renderers)).toBe("Launch plan");
  expect(titleOf("note", {}, renderers)).toBeNull();
  expect(titleOf("note", null, renderers)).toBeNull();
  expect(titleOf("note", "text", renderers)).toBeNull();
  expect(titleOf("note", [1, 2], renderers)).toBeNull();
  // A kind with no renderer is JSON, titled by its `title`.
  expect(titleOf("ticket", { title: "Printer is on fire" }, renderers)).toBe("Printer is on fire");
  expect(titleOf("ticket", { title: 4 }, renderers)).toBeNull();
});

test("the list's titles are by id, and what isn't an artifact is skipped", () => {
  const listed = [
    { id: "art_1", kind: "note", version: 1, data: { text: "First note" } },
    { id: "art_2", kind: "note", version: 1, data: { text: "" } },
    { id: "art_3", kind: "note" },
    { kind: "note", data: { text: "no id" } },
    { id: 4, kind: "note", data: { text: "id not text" } },
    null,
    "oddity",
  ];
  expect([...titlesOf(listed, renderers)]).toEqual([["art_1", "First note"]]);
  expect(titlesOf({ not: "a list" }, renderers).size).toBe(0);
  expect(titlesOf(undefined, renderers).size).toBe(0);
});

test("the app's own renderers title a form, a dashboard and an app by their titles", () => {
  for (const kind of ["form", "dashboard", "app"]) {
    expect(titleOf(kind, { title: "Lunch poll" })).toBe("Lunch poll");
  }
  expect(titleOf("note", { text: "Plain" })).toBe("Plain");
  expect(titleOf("submission", { form_id: "form_1", values: {} })).toBeNull();
});
