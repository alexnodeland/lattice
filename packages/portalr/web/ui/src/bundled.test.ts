import { expect, test } from "vitest";
import { type Bundled, loadedWithout, NATIVE_FILES } from "../bundled";

const chunk = (
  facadeModuleId: string | null,
  modules: readonly string[],
  links: { imports?: string[]; dynamicImports?: string[]; isEntry?: boolean } = {},
) => ({
  type: "chunk" as const,
  isEntry: links.isEntry ?? false,
  facadeModuleId,
  imports: links.imports ?? [],
  dynamicImports: links.dynamicImports ?? [],
  modules: Object.fromEntries(modules.map((id) => [id, {}])),
});

const FILES = "/web/app/src/on-demand/files.tsx";
const PARTS = "/web/app/src/native-file.tsx";
const PAGES = "/web/ui/src/file-pages.tsx";

/** An app whose route loads the native files' add-on, as it should, or imports it. */
const app = (route: { imports?: string[]; dynamicImports?: string[] }): Bundled => ({
  "index.js": chunk("/web/app/src/main.tsx", ["/web/app/src/main.tsx"], {
    isEntry: true,
    dynamicImports: ["route.js"],
  }),
  "route.js": chunk("/web/app/src/routes/artifact.tsx", ["/web/app/src/files.tsx"], route),
  "files.js": chunk(FILES, [FILES, PARTS], { imports: ["pages.js"] }),
  "pages.js": chunk(null, [PAGES]),
  "index.css": { type: "asset" },
});

test("the native files' parts loaded only with their add-on are not loaded without it", () => {
  expect(loadedWithout(app({ dynamicImports: ["files.js"] }), NATIVE_FILES)).toEqual([]);
});

test("an add-on imported statically, rather than loaded, loads its parts without it", () => {
  expect(loadedWithout(app({ imports: ["files.js"] }), NATIVE_FILES)).toEqual([
    FILES,
    PARTS,
    PAGES,
  ]);
});

test("a part a route holds itself loads without the add-on", () => {
  const bundle = app({ dynamicImports: ["files.js"] });
  const held = { ...bundle, "route.js": chunk(null, [PAGES], { dynamicImports: ["files.js"] }) };
  expect(loadedWithout(held, NATIVE_FILES)).toEqual([PAGES]);
});
