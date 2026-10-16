import type { BundledPackage } from "./collect";

/** What separates one package's entry from the next; the entries' headings follow it. */
export const SEPARATOR = "=".repeat(80);

/** The notices file for a UI: the same bundle always gives the same text, with no date in it. */
export function render(
  ui: string,
  packages: readonly BundledPackage[],
  /** Why a package that ships no licence text has none here: policy.json's reason. */
  reasons: ReadonlyMap<string, string> = new Map(),
): string {
  const entries = packages.map((found) => {
    const lines = [
      SEPARATOR,
      `## ${found.name}@${found.version}`,
      `Licence: ${found.licence ?? "none declared"}`,
    ];
    if (found.source !== undefined) {
      lines.push(`Source: ${found.source}`);
    }
    const reason = reasons.get(`${found.name}@${found.version}`);
    if (found.texts.length === 0 && reason !== undefined) {
      lines.push("", `This package ships no licence text. ${reason}`);
    }
    for (const { file, text } of found.texts) {
      lines.push("", `--- ${file}`, "", text);
    }
    return lines.join("\n");
  });
  return `${[
    `Third-party notices for the JavaScript in portalr's ${ui} UI`,
    "",
    `The ${packages.length} packages below are bundled into this UI. Their own licences and notices`,
    "follow, as they ship them. The typefaces' licences and Tremor's, whose charts the UI adapts,",
    "are with the wheel's licences.",
    "",
    "Generated at build time from the bundle by portalr's web/notices: not edited by hand.",
    ...entries.flatMap((entry) => ["", entry]),
  ].join("\n")}\n`;
}

/** The packages a notices file names, with the licence each declares: render's inverse. */
export function parseNotices(
  text: string,
): { name: string; version: string; licence: string; hasText: boolean }[] {
  return text
    .split(`\n${SEPARATOR}\n`)
    .slice(1)
    .flatMap((entry) => {
      const [heading = "", licence = ""] = entry.split("\n");
      const match = /^## (.+)@([^@\s]+)$/.exec(heading);
      return match?.[1] === undefined || match[2] === undefined
        ? []
        : [
            {
              name: match[1],
              version: match[2],
              licence: licence.replace(/^Licence: /, ""),
              hasText: entry.includes("\n--- "),
            },
          ];
    });
}
