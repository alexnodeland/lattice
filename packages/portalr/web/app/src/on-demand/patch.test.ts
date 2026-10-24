import { expect, test } from "vitest";
import fixture from "../../../../../artifactr/schemas/excalidraw_patches.json";
import { type ElementJson, elementPatch, rebase, type Scene, won } from "./patch";

const base = fixture.base as unknown as Scene;

test.each(fixture.cases)("patches as artifactr does: $case", ({ elements, files, ops }) => {
  expect(elementPatch(base, elements as unknown as Record<string, ElementJson>, files)).toEqual(
    ops,
  );
});

type Rebased = { local: Record<string, ElementJson>; head: Record<string, ElementJson> };

test.each(fixture.rebases)("rebases as artifactr does: $case", (each) => {
  const { local, head } = each as unknown as Rebased;
  const moved = rebase(base, local, { elements: head, files: {} });
  const written = Object.fromEntries(
    Object.entries(moved).map(([key, element]) => {
      const filled = { isDeleted: false, index: null, updated: null, ...element };
      const drawn =
        filled.versionNonce !== local[key]?.versionNonce &&
        filled.versionNonce !== head[key]?.versionNonce;
      return [key, { ...filled, versionNonce: drawn ? "new" : filled.versionNonce }];
    }),
  );
  expect(written).toEqual(each.rebased);
});

const at = (id: string, version: number, versionNonce: number, x = 0): ElementJson => ({
  id,
  type: "rectangle",
  version,
  versionNonce,
  x,
});

test("the higher version wins, and of one version the lower nonce", () => {
  expect(won(at("a", 3, 9), at("a", 2, 1))).toBe(true);
  expect(won(at("a", 2, 1), at("a", 2, 9))).toBe(true);
  expect(won(at("a", 2, 9), at("a", 2, 1))).toBe(false);
});

test("a stale edit is moved onto the head: what wins goes above the head, what loses is dropped", () => {
  const was: Scene = { elements: { r1: at("r1", 1, 10), r2: at("r2", 1, 10) }, files: {} };
  // Someone else moved r1 to version 2; this person moved r1 (version 2, a higher nonce) and r2.
  const head: Scene = { elements: { r1: at("r1", 2, 5, 50), r2: at("r2", 1, 10) }, files: {} };
  const mine = { r1: at("r1", 2, 9, 70), r2: at("r2", 2, 3, 90), new1: at("new1", 1, 1) };
  const moved = rebase(was, mine, head);
  expect(moved.r1).toEqual(head.elements.r1);
  expect([moved.r2?.version, moved.r2?.x]).toEqual([2, 90]);
  expect(moved.new1).toEqual(mine.new1);
  // r2 won the head's at its version, so it goes again at one above: still 2, the head's being 1.
  expect(moved.r2?.versionNonce).not.toBe(3);
  expect(elementPatch(head, moved).map((op) => op.path)).toEqual([
    "/elements/r2/version",
    "/elements/r2",
    "/elements/new1",
  ]);
});
