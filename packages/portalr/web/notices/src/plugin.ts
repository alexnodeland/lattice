import { existsSync, readFileSync } from "node:fs";
import type { Plugin } from "vite";
import { collect } from "./collect";
import { stylesheetPackages } from "./css";
import { check, type Policy, usedUnder } from "./policy";
import { type Note, render } from "./render";

/** The file each UI's build writes beside its index.html. */
export const NOTICES_FILE = "THIRD-PARTY-NOTICES.txt";

/**
 * Collects the licences of the packages in the UI's bundle, as the bundler built it, into
 * THIRD-PARTY-NOTICES.txt beside its files, and fails the build on a package the policy refuses.
 * A package tree-shaken out of the bundle is not in it, and one added to it is: JavaScript and
 * the stylesheets imported from it are in the bundler's list of modules, and what a stylesheet
 * `@import`s itself (`tailwindcss`) is read from the stylesheet's source.
 */
export function notices(options: { ui: string; policy: Policy }): Plugin {
  return {
    name: "portalr-notices",
    apply: "build",
    generateBundle(_, bundle) {
      const ids = new Set<string>();
      for (const output of Object.values(bundle)) {
        if (output.type === "chunk") {
          for (const id of Object.keys(output.modules)) {
            ids.add(id);
          }
        }
      }
      // A stylesheet the bundle holds is read from disk, as written: by the time a plugin sees
      // it in the build, Tailwind has already inlined its imports.
      for (const id of [...ids]) {
        const file = id.split("?")[0] ?? id;
        if (file.endsWith(".css") && existsSync(file)) {
          for (const found of stylesheetPackages(file, readFileSync(file, "utf8"))) {
            ids.add(found);
          }
        }
      }
      const packages = collect(ids);
      const problems = check(packages, options.policy);
      if (problems.length > 0) {
        this.error(
          `the ${options.ui} UI bundles ${problems.length} package(s) whose licence is not in order ` +
            `(web/notices/policy.json):\n${problems.map((p) => `  ${p.package}: ${p.message}`).join("\n")}`,
        );
      }
      const notes = new Map<string, Note>();
      for (const found of packages) {
        const excuse = options.policy.exceptions.find(
          (e) => e.kind === "text" && e.package === found.name && e.licence === found.licence,
        );
        const used =
          found.licence === undefined ? undefined : usedUnder(found.licence, options.policy);
        if (excuse !== undefined || used !== undefined) {
          notes.set(`${found.name}@${found.version}`, {
            ...(excuse === undefined ? {} : { reason: excuse.reason }),
            ...(used === undefined ? {} : { usedUnder: used.join(" AND ") }),
          });
        }
      }
      this.emitFile({
        type: "asset",
        fileName: NOTICES_FILE,
        source: render(options.ui, packages, notes),
      });
    },
  };
}
