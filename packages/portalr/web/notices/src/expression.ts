import type { Entry } from "./render";
import { ids, parse } from "./spdx";

/**
 * The licences the wheel's own code and files are under, beside the bundled packages': lattice's
 * MIT, the typefaces' OFL (web/ui/src/fonts), and Tremor's Apache-2.0 (web/ui/NOTICE).
 */
export const OWN_LICENCES = ["MIT", "OFL-1.1", "Apache-2.0"] as const;

/** The SPDX identifiers the notices say the bundled packages are used under, once each. */
export function bundledLicences(entries: readonly Entry[]): string[] {
  const found = new Map<string, string>();
  for (const entry of entries) {
    const expression = parse(entry.licence);
    // Where an OR was elected, the one used. Otherwise every identifier the expression names: for
    // a package a `licence` exception covers, whose licence isn't allowed, that is every
    // alternative, since none was elected, and the wheel's expression has to list them all.
    const used =
      entry.usedUnder?.split(" AND ") ?? (expression === undefined ? undefined : ids(expression));
    if (used === undefined) {
      throw new Error(`${entry.name}@${entry.version}: ${entry.licence} names no identifier`);
    }
    for (const id of used) {
      found.set(id.toLowerCase(), id);
    }
  }
  return [...found.values()].sort();
}

/**
 * What differs between the identifiers the wheel's `license` expression lists and those it
 * should: the bundled packages' (an `OR` by the one it is used under) and its own.
 */
export function expressionProblems(expression: string, bundled: readonly string[]): string[] {
  const parsed = parse(expression);
  if (parsed === undefined) {
    return [`the license expression, ${expression}, isn't SPDX`];
  }
  const listed = new Map(ids(parsed).map((id) => [id.toLowerCase(), id]));
  const expected = new Map([...OWN_LICENCES, ...bundled].map((id) => [id.toLowerCase(), id]));
  return [
    ...[...expected]
      .filter(([key]) => !listed.has(key))
      .map(([, id]) => `the license expression lacks ${id}, which is bundled`),
    ...[...listed]
      .filter(([key]) => !expected.has(key))
      .map(([, id]) => `the license expression lists ${id}, which nothing bundled is under`),
  ];
}
