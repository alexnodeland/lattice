import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";

/** A package whose code is in a bundle, with the licence it declares and the texts it ships. */
export interface BundledPackage {
  readonly name: string;
  readonly version: string;
  /** The licence as package.json declares it, as an SPDX expression; undefined where it doesn't. */
  readonly licence: string | undefined;
  readonly source: string | undefined;
  /** Its LICENSE, COPYING and NOTICE files: name and text, in name order. */
  readonly texts: readonly { readonly file: string; readonly text: string }[];
}

const IN_PACKAGE = /^(.*[\\/]node_modules[\\/])((?:@[^\\/]+[\\/])?[^\\/]+)[\\/]/;
const NOTICE_FILE = /^(licen[cs]e|copying|notice)([-_. ].*)?$/i;

/** The directory of the package a module id is in, or undefined for a module that isn't in one. */
export function packageDirectory(id: string): string | undefined {
  const match = IN_PACKAGE.exec(id.split("?")[0] ?? "");
  return match?.[1] === undefined || match[2] === undefined ? undefined : join(match[1], match[2]);
}

/** A declared licence as one expression: `license` as a string or `{type}`, or `licenses` as OR. */
export function declaredLicence(manifest: {
  readonly license?: unknown;
  readonly licenses?: unknown;
}): string | undefined {
  const one = (value: unknown): string | undefined => {
    if (typeof value === "string") {
      return value.trim() || undefined;
    }
    if (typeof value === "object" && value !== null && "type" in value) {
      return one(value.type);
    }
    return undefined;
  };
  const single = one(manifest.license);
  if (single !== undefined || !Array.isArray(manifest.licenses)) {
    return single;
  }
  const several = manifest.licenses.map(one);
  return several.length > 0 && several.every((licence) => licence !== undefined)
    ? `(${several.join(" OR ")})`
    : undefined;
}

function repository(manifest: { readonly repository?: unknown; readonly homepage?: unknown }) {
  const value = manifest.repository;
  const url = typeof value === "string" ? value : (value as { url?: unknown } | undefined)?.url;
  if (typeof url === "string") {
    return url.replace(/^git\+/, "");
  }
  return typeof manifest.homepage === "string" ? manifest.homepage : undefined;
}

/** The notice files in a directory, name and text, in name order. */
function noticesIn(directory: string): string[] {
  return readdirSync(directory)
    .filter((file) => NOTICE_FILE.test(file) && statSync(join(directory, file)).isFile())
    .sort();
}

/**
 * The package at `directory`, with the notice files at its root and those in the directories
 * above the modules of it that are bundled: a package that vendors others (victory-vendor's d3
 * modules) keeps their licences beside them.
 */
function read(directory: string, modules: readonly string[]): BundledPackage {
  const manifest = JSON.parse(readFileSync(join(directory, "package.json"), "utf8")) as {
    name?: string;
    version?: string;
    license?: unknown;
    licenses?: unknown;
    repository?: unknown;
    homepage?: unknown;
  };
  const holders = new Set([directory]);
  for (const module of modules) {
    for (let at = dirname(module); at.length > directory.length; at = dirname(at)) {
      holders.add(at);
    }
  }
  const files = [...holders]
    .flatMap((holder) => noticesIn(holder).map((file) => relative(directory, join(holder, file))))
    .sort((a, b) => a.localeCompare(b, "en"));
  return {
    name: manifest.name ?? directory,
    version: manifest.version ?? "0.0.0",
    licence: declaredLicence(manifest),
    source: repository(manifest),
    texts: files.map((file) => ({
      file,
      text: readFileSync(join(directory, file), "utf8").replace(/\r\n?/g, "\n").trim(),
    })),
  };
}

/**
 * The packages the modules of a bundle are from, once each, in name and version order. A module
 * outside `node_modules` is lattice's own, and a virtual module (`\0…`) has no file.
 */
export function collect(moduleIds: Iterable<string>): BundledPackage[] {
  const directories = new Map<string, string[]>();
  for (const id of moduleIds) {
    const directory = id.startsWith("\0") ? undefined : packageDirectory(id);
    if (directory !== undefined && existsSync(join(directory, "package.json"))) {
      directories.set(directory, [...(directories.get(directory) ?? []), id.split("?")[0] ?? id]);
    }
  }
  const unique = new Map<string, BundledPackage>();
  for (const [directory, modules] of directories) {
    const found = read(directory, modules);
    unique.set(`${found.name}@${found.version}`, found);
  }
  return [...unique.values()].sort(
    (a, b) =>
      a.name.localeCompare(b.name, "en") ||
      a.version.localeCompare(b.version, "en", { numeric: true }),
  );
}
