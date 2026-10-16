import { type BundledPackage, isLicenceFile } from "./collect";

/** What separates one package's entry from the next; a heading (`## name@version`) follows it. */
export const SEPARATOR = "=".repeat(80);

/** Where one entry ends: the separator, and the next entry's heading. A licence text can hold neither. */
const BETWEEN_ENTRIES = new RegExp(`\\n${SEPARATOR}\\n(?=## )`);

/** What the notices add to a package's entry: why it has no text, and the licence it is used under. */
export interface Note {
  readonly reason?: string;
  readonly usedUnder?: string;
}

/** The notices file for a UI: the same bundle always gives the same text, with no date in it. */
export function render(
  ui: string,
  packages: readonly BundledPackage[],
  notes: ReadonlyMap<string, Note> = new Map(),
): string {
  const entries = packages.map((found) => {
    const key = `${found.name}@${found.version}`;
    const note = notes.get(key);
    const lines = [SEPARATOR, `## ${key}`, `Licence: ${found.licence ?? "none declared"}`];
    if (note?.usedUnder !== undefined) {
      lines.push(`Used under: ${note.usedUnder}`);
    }
    if (found.source !== undefined) {
      lines.push(`Source: ${found.source}`);
    }
    if (!found.texts.some(({ file }) => isLicenceFile(file)) && note?.reason !== undefined) {
      lines.push("", `This package ships no licence text. ${note.reason}`);
    }
    for (const { file, text } of found.texts) {
      if (BETWEEN_ENTRIES.test(`\n${text}\n`)) {
        throw new Error(`${key}'s ${file} holds the line that separates the notices' entries`);
      }
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

export interface Entry {
  readonly name: string;
  readonly version: string;
  readonly licence: string;
  /** Where the licence offered a choice: what it is used under. */
  readonly usedUnder: string | undefined;
  /** Whether the entry holds a LICENSE or COPYING text, not only a NOTICE. */
  readonly hasText: boolean;
}

/** The packages a notices file names, with the licence each declares: render's inverse. */
export function parseNotices(text: string): Entry[] {
  return text
    .split(BETWEEN_ENTRIES)
    .slice(1)
    .map((entry) => {
      const [heading = "", licence = "", used = ""] = entry.split("\n");
      const match = /^## (.+)@([^@\s]+)$/.exec(heading);
      if (match?.[1] === undefined || match[2] === undefined) {
        throw new Error(`a notices entry has no heading of the form "## name@version": ${heading}`);
      }
      return {
        name: match[1],
        version: match[2],
        licence: licence.replace(/^Licence: /, ""),
        usedUnder: used.startsWith("Used under: ") ? used.slice("Used under: ".length) : undefined,
        hasText: [...entry.matchAll(/^--- (.+)$/gm)].some(([, file = ""]) => isLicenceFile(file)),
      };
    });
}
