import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, expect, test } from "vitest";
import { LIBERATION, LIBERATION_URI, replaceLiberation } from "./liberation";

const roots: string[] = [];
afterAll(() => {
  for (const root of roots) {
    rmSync(root, { recursive: true, force: true });
  }
});

/** A `fonts` directory whose Liberation directory holds these files, and a replacement. */
function fonts(...held: string[]): { fonts: string; replacement: string } {
  const root = mkdtempSync(join(tmpdir(), "liberation-"));
  roots.push(root);
  mkdirSync(join(root, "Liberation"), { recursive: true });
  for (const name of held) {
    writeFileSync(join(root, "Liberation", name), "excalidraw's");
  }
  const replacement = join(root, "replacement.woff2");
  writeFileSync(replacement, "2.1.5");
  return { fonts: root, replacement };
}

test("the file Excalidraw ships is replaced by the replacement", () => {
  const { fonts: dir, replacement } = fonts("LiberationSans-Regular.woff2");
  replaceLiberation(dir, replacement);
  expect(readFileSync(join(dir, "Liberation", "LiberationSans-Regular.woff2"), "utf8")).toBe(
    "2.1.5",
  );
});

test("a directory that holds anything else, or nothing, is refused", () => {
  for (const held of [[], ["LiberationSans-Bold.woff2"], ["LiberationSans-Regular.woff2", "x"]]) {
    const { fonts: dir, replacement } = fonts(...held);
    expect(() => replaceLiberation(dir, replacement)).toThrow(/Liberation Sans isn't/);
  }
  const root = mkdtempSync(join(tmpdir(), "liberation-"));
  roots.push(root);
  expect(() => replaceLiberation(root)).toThrow(/\(none\)/);
});

test("the replacement is the committed file, and Excalidraw's code names the file by its address", () => {
  expect(readFileSync(LIBERATION).subarray(0, 4).toString()).toBe("wOF2");
  expect(LIBERATION_URI).toBe("fonts/Liberation/LiberationSans-Regular.woff2");
});
