import type { Plugin } from "vite";
import { collect } from "./collect";
import { check, type Policy } from "./policy";
import { render } from "./render";

/** The file each UI's build writes beside its index.html. */
export const NOTICES_FILE = "THIRD-PARTY-NOTICES.txt";

/**
 * Collects the licences of the packages in the UI's bundle, as the bundler built it, into
 * THIRD-PARTY-NOTICES.txt beside its files, and fails the build on a package the policy refuses.
 * A package tree-shaken out of the bundle is not in it, and one added to it is.
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
      const packages = collect(ids);
      const problems = check(packages, options.policy);
      if (problems.length > 0) {
        this.error(
          `the ${options.ui} UI bundles ${problems.length} package(s) whose licence is not in order ` +
            `(web/notices/policy.json):\n${problems.map((p) => `  ${p.package}: ${p.message}`).join("\n")}`,
        );
      }
      const reasons = new Map(
        packages.flatMap((found) => {
          const excuse = options.policy.exceptions.find(
            (e) => e.kind === "text" && e.package === found.name && e.licence === found.licence,
          );
          return excuse === undefined
            ? []
            : [[`${found.name}@${found.version}`, excuse.reason] as const];
        }),
      );
      this.emitFile({
        type: "asset",
        fileName: NOTICES_FILE,
        source: render(options.ui, packages, reasons),
      });
    },
  };
}
