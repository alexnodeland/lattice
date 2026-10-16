import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterAll, beforeAll, expect, test } from "vitest";
import { stylesheetPackages } from "./css";

const root = mkdtempSync(join(tmpdir(), "notices-css-"));
const entry = join(root, "src", "main.css");
beforeAll(() => mkdirSync(join(root, "src")));
afterAll(() => rmSync(root, { recursive: true, force: true }));

function pack(name: string, files: Record<string, string>, manifest: object = {}) {
  const directory = join(root, "node_modules", name);
  mkdirSync(directory, { recursive: true });
  writeFileSync(
    join(directory, "package.json"),
    JSON.stringify({ name, version: "1.0.0", ...manifest }),
  );
  for (const [file, text] of Object.entries(files)) {
    mkdirSync(dirname(join(directory, file)), { recursive: true });
    writeFileSync(join(directory, file), text);
  }
}

const found = (code: string) =>
  stylesheetPackages(entry, code)
    .map((file) => file.replace(root, ""))
    .sort();

test("a stylesheet's package imports are found, through relative files and package files", () => {
  pack("plain", {});
  pack("@scope/kit", {
    "base.css": '@import "./theme.css";',
    "theme.css": '@import "deep/x.css";',
  });
  pack("deep", { "x.css": "" });
  pack("commented", {});
  writeFileSync(join(root, "src", "tokens.css"), "@import 'plain';");
  expect(
    found(
      [
        '@import url("@scope/kit/base.css") layer(base);',
        '@import "./tokens.css";',
        '@import "https://fonts.example.com/x.css";',
        '/* @import "commented"; */',
        '@import "not-installed";',
      ].join("\n"),
    ),
  ).toEqual([
    "/node_modules/@scope/kit/package.json",
    "/node_modules/deep/package.json",
    "/node_modules/plain/package.json",
  ]);
});

test("an unquoted url() is a specifier too, and a quoted remote one is not", () => {
  pack("unquoted", {});
  expect(
    found("@import url(unquoted/x.css);\n@import url('https://cdn.example.com/y.css');"),
  ).toEqual(["/node_modules/unquoted/package.json"]);
});

test("a package's exports map gives its stylesheet under the style condition", () => {
  pack(
    "mapped",
    { "dist/mapped.css": '@import "behind-the-map";' },
    {
      exports: {
        ".": { types: "./index.d.ts", style: "./dist/mapped.css", default: "./index.js" },
        "./extra": "./dist/extra.css",
      },
    },
  );
  pack("behind-the-map", {});
  pack("fielded", { "f.css": '@import "behind-the-field";' }, { style: "f.css" });
  pack("behind-the-field", {});
  pack(
    "sub",
    { "dist/extra.css": '@import "behind-the-sub";' },
    { exports: { "./extra": "./dist/extra.css" } },
  );
  pack("behind-the-sub", {});
  expect(found('@import "mapped";')).toEqual([
    "/node_modules/behind-the-map/package.json",
    "/node_modules/mapped/package.json",
  ]);
  expect(found('@import "fielded";')).toEqual([
    "/node_modules/behind-the-field/package.json",
    "/node_modules/fielded/package.json",
  ]);
  expect(found('@import "sub/extra";')).toEqual([
    "/node_modules/behind-the-sub/package.json",
    "/node_modules/sub/package.json",
  ]);
});

test("a workspace package, linked from outside node_modules, is lattice's own", () => {
  const own = join(root, "workspace", "ui");
  mkdirSync(own, { recursive: true });
  writeFileSync(join(own, "package.json"), JSON.stringify({ name: "@own/ui", version: "0.0.0" }));
  writeFileSync(join(own, "styles.css"), '@import "from-the-workspace";');
  pack("from-the-workspace", {});
  mkdirSync(join(root, "node_modules", "@own"), { recursive: true });
  symlinkSync(own, join(root, "node_modules", "@own", "ui"));
  expect(found('@import "@own/ui/styles.css";')).toEqual([]);
});

test("stylesheets that import each other are each read once", () => {
  pack("cyclic", {});
  writeFileSync(join(root, "src", "a.css"), '@import "./b.css"; @import "cyclic";');
  writeFileSync(join(root, "src", "b.css"), '@import "./a.css";');
  expect(found('@import "./a.css";')).toEqual(["/node_modules/cyclic/package.json"]);
});

test("an absolute path is followed, and one that isn't there is not", () => {
  pack("by-path", {});
  const absolute = join(root, "src", "absolute.css");
  writeFileSync(absolute, '@import "by-path";');
  expect(found(`@import "${absolute}";\n@import "/abs.css";`)).toEqual([
    "/node_modules/by-path/package.json",
  ]);
});
