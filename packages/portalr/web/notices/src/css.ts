import { existsSync, readFileSync, realpathSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { findPackageDirectory } from "./collect";

// A quoted specifier, or an unquoted one in `url(...)`.
const IMPORT = /@import\s+(?:url\(\s*)?(?:["']([^"']+)["']|([^\s"')]+))/g;

/** A string, or the value of the `style` condition, `import` or `default` in an exports target. */
function target(value: unknown): string | undefined {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "object" && value !== null) {
    for (const condition of ["style", "import", "default"]) {
      const found = target((value as Record<string, unknown>)[condition]);
      if (found !== undefined) {
        return found;
      }
    }
  }
  return undefined;
}

/**
 * The stylesheet a package's import of `subpath` names ("" for the package itself): the file its
 * exports map gives for it under the `style` condition, else its `style` field, else the path.
 */
function stylesheetOf(directory: string, subpath: string): string | undefined {
  const manifest = JSON.parse(readFileSync(join(directory, "package.json"), "utf8")) as {
    exports?: unknown;
    style?: unknown;
  };
  const exported =
    typeof manifest.exports === "object" && manifest.exports !== null
      ? (manifest.exports as Record<string, unknown>)
      : undefined;
  const key = subpath === "" ? "." : `./${subpath}`;
  const mapped = exported && key in exported ? target(exported[key]) : undefined;
  if (mapped !== undefined) {
    return join(directory, mapped);
  }
  if (subpath === "") {
    return typeof manifest.style === "string" ? join(directory, manifest.style) : undefined;
  }
  return join(directory, subpath);
}

/** Whether the package is installed from outside (a registry's copy), not a workspace's own. */
const isInstalled = (directory: string) => /[\\/]node_modules[\\/]/.test(realpathSync(directory));

/**
 * The packages a stylesheet `@import`s, as the package.json of each: the bundler's module list
 * has JavaScript and the CSS files imported from it, but not what a stylesheet pulls in itself
 * (`@import "tailwindcss"`), which the build copies into the UI's styles all the same. Relative
 * and absolute imports, and the stylesheet a package's exports map gives under the `style`
 * condition (or its `style` field, or the path), are followed for what they import in turn. A
 * workspace package, whose real path is outside `node_modules`, is lattice's own and is left out.
 */
export function stylesheetPackages(file: string, code: string, seen = new Set<string>()): string[] {
  if (seen.has(file)) {
    return [];
  }
  seen.add(file);
  const found: string[] = [];
  for (const [, quoted, bare] of code.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(IMPORT)) {
    const specifier = quoted ?? bare ?? "";
    if (/^(https?:|data:|\/\/)/.test(specifier)) {
      continue;
    }
    let next: string | undefined;
    if (specifier.startsWith(".") || specifier.startsWith("/")) {
      next = resolve(dirname(file), specifier);
    } else {
      const [first = "", second = "", ...rest] = specifier.split("/");
      const name = first.startsWith("@") ? `${first}/${second}` : first;
      const subpath = (first.startsWith("@") ? rest : [second, ...rest]).filter(Boolean).join("/");
      const directory = findPackageDirectory(name, dirname(file));
      if (directory === undefined || !isInstalled(directory)) {
        continue;
      }
      found.push(join(directory, "package.json"));
      next = stylesheetOf(directory, subpath);
    }
    if (next?.endsWith(".css") && existsSync(next)) {
      found.push(...stylesheetPackages(next, readFileSync(next, "utf8"), seen));
    }
  }
  return found;
}
