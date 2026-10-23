import { expect, test } from "vitest";
import * as files from "./files";

test("the native files' add-on holds each part a page places", () => {
  expect(Object.keys(files).sort()).toEqual([
    "NativeFile",
    "NativeInline",
    "NativeProposal",
    "TextChanges",
  ]);
});
