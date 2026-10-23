/**
 * Checks of what a UI's build holds, which fail the build: app's, admin's and the CSP harness's
 * Vite configs use them.
 */

import type { Plugin } from "vite";
import { loadedWithout } from "./bundled";

export { NATIVE_FILES } from "./bundled";

/**
 * Fails the build where a module that `heavy` matches loads with the entry, rather than with the
 * routes that use it: Recharts is Feedback's and Usage's, so the first page doesn't wait on it.
 */
export function lean(heavy: RegExp): Plugin {
  return {
    name: "lean",
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
 * `rehype-raw` and what only it brings: parse5 and the hast utilities around it, which Streamdown
 * imports and portalr never uses, since it never passes HTML through (portalr ADR-0040).
 */
export const RAW_HTML =
  /[\\/]node_modules[\\/](rehype-raw|parse5|hast-util-raw|hast-util-from-parse5|hast-util-to-parse5)[\\/]/;

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

/**
 * Fails the build where a module that `addon` matches loads without its add-on, such as the
 * native files' parts, which are the native files' add-on's alone (portalr ADR-0044).
 */
export function onDemand(addon: RegExp): Plugin {
  return {
    name: "on-demand",
    generateBundle(_, bundle) {
      const found = loadedWithout(bundle, addon);
      if (found.length > 0) {
        this.error(
          `${found.length} modules load without their add-on that shouldn't, such as ${found[0]}`,
        );
      }
    },
  };
}
