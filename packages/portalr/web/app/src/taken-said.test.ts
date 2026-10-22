import { expect, test } from "vitest";
import { takenSaid } from "./upload";

test("no extensions: nothing to name", () => {
  expect(takenSaid([])).toBeNull();
});

test("one extension is named alone", () => {
  expect(takenSaid([".docx"])).toBe(".docx");
});

test("each extension once, by its first spelling, as the server sent it", () => {
  expect(takenSaid([".DXF", ".docx", ".dxf", ".docx"])).toBe(".DXF or .docx");
});

test("several are a list ending in or", () => {
  expect(takenSaid([".docx", ".dwg", ".fcproj"])).toBe(".docx, .dwg, or .fcproj");
});

test("a long list names five and says how many more", () => {
  const many = Array.from({ length: 9 }, (_, i) => `.e${i}`);
  expect(takenSaid(many)).toBe(".e0, .e1, .e2, .e3, .e4, or 4 more");
});

test("the order is the server's, by each extension's first appearance", () => {
  expect(takenSaid([".b", ".a", ".B", ".c", ".a"])).toBe(".b, .a, or .c");
});
