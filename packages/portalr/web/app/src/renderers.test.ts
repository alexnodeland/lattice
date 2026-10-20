import { expect, test } from "vitest";
import { NATIVE, RENDERERS } from "./renderers";
import { titleOf } from "./titles";

test("each native file's kind is shown as a native file, and switched by its app's key", () => {
  expect([...NATIVE.keys()]).toEqual([
    "word_document",
    "workbook",
    "presentation",
    "pdf_document",
    "drawing",
    "layered_image",
    "vector_image",
    "page_layout",
    "design",
    "cad_model",
  ]);
  for (const [kind, native] of NATIVE) {
    expect(RENDERERS.has(kind)).toBe(true);
    expect(titleOf(kind, { name: `budget.${kind}` })).toBe(`budget.${kind}`);
    expect(native.integration).toBe(`files:${native.app.toLowerCase()}`);
  }
});
