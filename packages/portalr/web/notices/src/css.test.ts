import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, expect, test } from "vitest";
import { stylesheetPackages } from "./css";

const root = mkdtempSync(join(tmpdir(), "notices-css-"));
afterAll(() => rmSync(root, { recursive: true, force: true }));

function pack(name: string, files: Record<string, string>) {
  const directory = join(root, "node_modules", name);
  mkdirSync(directory, { recursive: true });
  writeFileSync(join(directory, "package.json"), JSON.stringify({ name, version: "1.0.0" }));
  for (const [file, text] of Object.entries(files)) {
    writeFileSync(join(directory, file), text);
  }
}

test("a stylesheet's package imports are found, through relative files and package files", () => {
  pack("plain", {});
  pack("@scope/kit", {
    "base.css": '@import "./theme.css";',
    "theme.css": '@import "deep/x.css";',
  });
  pack("deep", { "x.css": "" });
  pack("commented", {});
  mkdirSync(join(root, "src"));
  const entry = join(root, "src", "main.css");
  const code = [
    '@import "tailwind-less";',
    '@import url("@scope/kit/base.css") layer(base);',
    '@import "./tokens.css";',
    '@import "https://fonts.example.com/x.css";',
    '/* @import "commented"; */',
    '@import "not-installed";',
  ].join("\n");
  writeFileSync(join(root, "src", "tokens.css"), "@import 'plain';");
  const found = stylesheetPackages(entry, code).map((file) => file.replace(root, ""));
  expect(found.sort()).toEqual([
    "/node_modules/@scope/kit/package.json",
    "/node_modules/deep/package.json",
    "/node_modules/plain/package.json",
  ]);
});

test("a stylesheet that imports itself again is read once", () => {
  const file = join(root, "src", "loop.css");
  writeFileSync(file, '@import "./loop.css";');
  expect(stylesheetPackages(file, '@import "./loop.css";')).toEqual([]);
});
