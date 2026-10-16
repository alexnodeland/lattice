import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { findPackageDirectory } from "./collect";

const IMPORT = /@import\s+(?:url\(\s*)?["']([^"']+)["']/g;

/**
 * The packages a stylesheet `@import`s, as the package.json of each: the bundler's module list
 * has JavaScript and the CSS files imported from it, but not what a stylesheet pulls in itself
 * (`@import "tailwindcss"`), which the build copies into the UI's styles all the same. Relative
 * imports and the package files imported are followed for what they import in turn.
 */
export function stylesheetPackages(file: string, code: string, seen = new Set<string>()): string[] {
  if (seen.has(file)) {
    return [];
  }
  seen.add(file);
  const found: string[] = [];
  for (const [, specifier = ""] of code.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(IMPORT)) {
    if (/^(https?:|data:|\/\/)/.test(specifier)) {
      continue;
    }
    let target: string | undefined;
    if (specifier.startsWith(".") || specifier.startsWith("/")) {
      target = resolve(dirname(file), specifier);
    } else {
      const [first = "", second = "", ...rest] = specifier.split("/");
      const name = first.startsWith("@") ? `${first}/${second}` : first;
      const subpath = (first.startsWith("@") ? rest : [second, ...rest]).filter(Boolean).join("/");
      const directory = findPackageDirectory(name, dirname(file));
      if (directory === undefined) {
        continue;
      }
      found.push(join(directory, "package.json"));
      target = subpath === "" ? undefined : join(directory, subpath);
    }
    if (target?.endsWith(".css") && existsSync(target)) {
      found.push(...stylesheetPackages(target, readFileSync(target, "utf8"), seen));
    }
  }
  return found;
}
