import { readFileSync } from "node:fs";
import { type BundledPackage, isLicenceFile } from "./collect";
import type { Expression } from "./spdx";
import { allows, elect, offersChoice, parse } from "./spdx";

/**
 * A package that is fine though it breaks the policy, for a reason, as long as it declares the
 * licence named: `licence` where that isn't allowed, `text` where it ships no licence text.
 */
export interface Exception {
  readonly package: string;
  readonly licence: string;
  readonly kind: "licence" | "text";
  readonly reason: string;
}

export interface Policy {
  readonly allowed: readonly string[];
  readonly exceptions: readonly Exception[];
}

export interface Problem {
  readonly package: string;
  readonly message: string;
}

/** policy.json, read and checked to be what it should be. */
export function readPolicy(file: URL | string): Policy {
  const policy = JSON.parse(readFileSync(file, "utf8")) as Partial<Policy>;
  const { allowed, exceptions } = policy;
  if (!Array.isArray(allowed) || !allowed.every((id) => typeof id === "string")) {
    throw new Error(`${String(file)}: "allowed" is a list of SPDX identifiers`);
  }
  if (
    !Array.isArray(exceptions) ||
    !exceptions.every(
      (e) =>
        typeof e?.package === "string" &&
        typeof e.licence === "string" &&
        (e.kind === "licence" || e.kind === "text") &&
        typeof e.reason === "string" &&
        e.reason.trim() !== "",
    )
  ) {
    throw new Error(
      `${String(file)}: each exception names a package, its licence and a kind, with a reason`,
    );
  }
  const keys = exceptions.map((e) => `${e.kind} ${e.package} ${e.licence}`);
  const repeated = keys.find((key, at) => keys.indexOf(key) !== at);
  if (repeated !== undefined) {
    throw new Error(`${String(file)}: the exception "${repeated}" is there twice`);
  }
  return { allowed, exceptions };
}

const allowedIds = (policy: Policy) => new Set(policy.allowed.map((id) => id.toLowerCase()));

/** Whether the declared licence is within the allowlist, apart from exceptions. */
function permitted(licence: string, policy: Policy): boolean {
  const expression = parse(licence);
  return expression !== undefined && allows(expression, allowedIds(policy));
}

/**
 * Where the declared licence offers a choice (`MIT OR GPL-3.0-only`), the licences it is used
 * under: its first allowed alternative. Undefined where there is no choice, or none is allowed.
 */
export function usedUnder(licence: string, policy: Policy): string[] | undefined {
  const expression: Expression | undefined = parse(licence);
  return expression !== undefined && offersChoice(expression)
    ? elect(expression, allowedIds(policy))
    : undefined;
}

const excused = (
  policy: Policy,
  name: string,
  licence: string | undefined,
  kind: Exception["kind"],
) => policy.exceptions.some((e) => e.kind === kind && e.package === name && e.licence === licence);

/**
 * What stops these packages being shipped: no declared licence, a licence that isn't SPDX or isn't
 * allowed, or no licence text; the last two unless an exception covers that package and exactly
 * the licence it declares.
 */
export function check(packages: readonly BundledPackage[], policy: Policy): Problem[] {
  const problems: Problem[] = [];
  for (const found of packages) {
    const name = `${found.name}@${found.version}`;
    const { licence } = found;
    if (licence === undefined) {
      problems.push({ package: name, message: "declares no licence" });
    } else if (!permitted(licence, policy) && !excused(policy, found.name, licence, "licence")) {
      const kind = parse(licence) === undefined ? "isn't an SPDX expression" : "isn't allowed";
      problems.push({ package: name, message: `its licence, ${licence}, ${kind}` });
    }
    if (
      !found.texts.some(({ file }) => isLicenceFile(file)) &&
      !excused(policy, found.name, licence, "text")
    ) {
      problems.push({ package: name, message: "ships no LICENSE or COPYING file" });
    }
  }
  return problems;
}

/** The exceptions no bundled package needs: it isn't bundled, declares another licence, or passes. */
export function staleExceptions(
  bundled: readonly {
    readonly name: string;
    readonly licence: string | undefined;
    readonly hasText: boolean;
  }[],
  policy: Policy,
): Problem[] {
  const needed = (e: Exception) =>
    bundled.some(
      (found) =>
        found.name === e.package &&
        found.licence === e.licence &&
        (e.kind === "text" ? !found.hasText : !permitted(e.licence, policy)),
    );
  return policy.exceptions
    .filter((e) => !needed(e))
    .map((e) => ({
      package: e.package,
      message: `the ${e.kind} exception for ${e.licence} is in no UI's bundle, or isn't needed: remove it`,
    }));
}
