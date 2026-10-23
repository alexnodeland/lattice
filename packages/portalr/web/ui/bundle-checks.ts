/**
 * Checks of what a UI's build holds, which fail the build: app's and admin's Vite configs use them.
 */

import type { Plugin } from "vite";

/**
 * Fails the build where a module that `heavy` matches loads with the entry, rather than with the
 * routes that use it: Recharts is Feedback's and Usage's, so the first page doesn't wait on it.
 */
export function lean(heavy: RegExp): Plugin {
  return {
    name: "lean-entry",
    generateBundle(_, bundle) {
      const loaded = new Set<string>();
      const load = (file: string) => {
        const chunk = bundle[file];
        if (loaded.has(file) || chunk?.type !== "chunk") {
          return;
        }
        loaded.add(file);
        chunk.imports.forEach(load);
      };
      for (const [file, chunk] of Object.entries(bundle)) {
        if (chunk.type === "chunk" && chunk.isEntry) {
          load(file);
        }
      }
      const heavyModules = [...loaded].flatMap((file) => {
        const chunk = bundle[file];
        return chunk?.type === "chunk"
          ? Object.keys(chunk.modules).filter((id) => heavy.test(id))
          : [];
      });
      if (heavyModules.length > 0) {
        this.error(
          `the entry loads ${heavyModules.length} modules it shouldn't, such as ${heavyModules[0]}`,
        );
      }
    },
  };
}

/**
 * Fails the build where any chunk holds a module that `dead` matches: code the UI must never ship,
 * such as `rehype-raw` and parse5, which Streamdown imports and portalr never uses (portalr
 * ADR-0040).
 */
export function absent(dead: RegExp): Plugin {
  return {
    name: "absent",
    generateBundle(_, bundle) {
      const found = Object.values(bundle).flatMap((chunk) =>
        chunk.type === "chunk" ? Object.keys(chunk.modules).filter((id) => dead.test(id)) : [],
      );
      if (found.length > 0) {
        this.error(`the build holds ${found.length} modules it shouldn't, such as ${found[0]}`);
      }
    },
  };
}
