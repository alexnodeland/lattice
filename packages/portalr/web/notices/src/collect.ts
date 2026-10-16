import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";

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

const IN_PACKAGE = /^(.*\/node_modules\/)((?:@[^/]+\/)?[^/]+)\//;
/**
 * A notice file: LICENSE, LICENCE, LICENSES, COPYING, COPYRIGHT, UNLICENSE or NOTICE, bare, with
 * `.md`, `.txt` or `.rst`, or with a `-NAME` such as LICENSE-MIT. Not a source file that is
 * named so (`license.js`, `notice.ts`, `license.d.ts`, `license.js.map`).
 */
const NOTICE_FILE =
  /^(licen[cs]es?|copying|copyright|unlicense|notice)([-_][\w-]+)?(\.(md|markdown|txt|rst))?$/i;
/** Of those, the ones that are the licence's text: a package with only a NOTICE has not got it. */
const LICENCE_FILE = /^(licen[cs]es?|copying|unlicense)/i;

export const isLicenceFile = (file: string) => LICENCE_FILE.test(file);

/** Whether a file of a package's root is one whose text the notices carry. */
export const isNoticeFile = (file: string) => NOTICE_FILE.test(file);

/** Code units, not the locale's collation (which depends on ICU): the same order everywhere. */
const compare = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

/** Versions by their numbers where they have them, `1.10.0` after `1.9.0`. */
function compareVersions(a: string, b: string): number {
  const left = a.split(/(\d+)/);
  const right = b.split(/(\d+)/);
  for (let at = 0; at < Math.max(left.length, right.length); at += 1) {
    const x = left[at] ?? "";
    const y = right[at] ?? "";
    const order = at % 2 === 1 ? Number(x) - Number(y) : compare(x, y);
    if (order !== 0) {
      return Math.sign(order);
    }
  }
  return 0;
}

/**
 * The directory of the package a module id is in, or undefined for a module that isn't in one
 * (a directory of `node_modules` that starts with a dot, such as `.bun` or `.vite`, isn't one).
 */
export function packageDirectory(id: string): string | undefined {
  const match = IN_PACKAGE.exec((id.split("?")[0] ?? "").replaceAll("\\", "/"));
  if (match?.[1] === undefined || match[2] === undefined || match[2].startsWith(".")) {
    return undefined;
  }
  return join(match[1], match[2]);
}

/** The directory of the package `name`, as `from` or a directory above it has it installed. */
export function findPackageDirectory(name: string, from: string): string | undefined {
  for (let at = from; ; at = dirname(at)) {
    const candidate = join(at, "node_modules", name);
    if (existsSync(join(candidate, "package.json"))) {
      return candidate;
    }
    if (dirname(at) === at) {
      return undefined;
    }
  }
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

/** The package at `directory`, with the notice files at its root. */
function read(directory: string): BundledPackage {
  const file = join(directory, "package.json");
  if (!existsSync(file)) {
    // Fail closed: code of a package that can't be named can't be noticed.
    throw new Error(`${directory} holds bundled code but has no package.json`);
  }
  const manifest = JSON.parse(readFileSync(file, "utf8")) as {
    name?: string;
    version?: string;
    license?: unknown;
    licenses?: unknown;
    repository?: unknown;
    homepage?: unknown;
  };
  if (typeof manifest.name !== "string" || typeof manifest.version !== "string") {
    throw new Error(`${file} has no name and version: a package it bundles can't be noticed`);
  }
  const files = readdirSync(directory)
    .filter((entry) => isNoticeFile(entry) && statSync(join(directory, entry)).isFile())
    .sort();
  return {
    name: manifest.name,
    version: manifest.version,
    licence: declaredLicence(manifest),
    source: repository(manifest),
    texts: files.map((entry) => ({
      file: entry,
      text: readFileSync(join(directory, entry), "utf8").replace(/\r\n?/g, "\n").trim(),
    })),
  };
}

/**
 * The packages the modules of a bundle are from, once each, in name and version order. A module
 * outside `node_modules` is lattice's own, and a virtual module (`\0…`) has no file. Code from a
 * package that can't be read throws, rather than going unnoticed.
 */
export function collect(moduleIds: Iterable<string>): BundledPackage[] {
  const directories = new Set<string>();
  for (const id of moduleIds) {
    const directory = id.startsWith("\0") ? undefined : packageDirectory(id);
    if (directory !== undefined) {
      directories.add(directory);
    }
  }
  const unique = new Map<string, BundledPackage>();
  for (const directory of directories) {
    const found = read(directory);
    unique.set(`${found.name}@${found.version}`, found);
  }
  return [...unique.values()].sort(
    (a, b) => compare(a.name, b.name) || compareVersions(a.version, b.version),
  );
}
