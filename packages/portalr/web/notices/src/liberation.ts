import { cpSync, existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Liberation Sans 2.1.5 as WOFF2, which the builds that ship Excalidraw's faces copy over its
 * Liberation Sans: Excalidraw's is 1.05, whose licence is not the SIL Open Font License (lattice#679;
 * its notice, with the pins and checksums, is in ui/licenses/excalidraw-faces.txt).
 */
export const LIBERATION = fileURLToPath(
  new URL("../../ui/fonts/LiberationSans-Regular.woff2", import.meta.url),
);

/** Where Excalidraw 0.18.1 puts its Liberation Sans, under its fonts, and the one file it holds. */
const DIRECTORY = "Liberation";
const FILE = "LiberationSans-Regular.woff2";

/** The address Excalidraw's code names that file by, which a build checks it still does. */
export const LIBERATION_URI = `fonts/${DIRECTORY}/${FILE}`;

/**
 * Copy Liberation Sans 2.1.5 over Excalidraw's, in the `fonts` directory a build wrote.
 *
 * @throws if that directory doesn't hold the one file Excalidraw ships, which means Excalidraw's
 *   faces are not what this replaces: check them again before the build ships either.
 */
export function replaceLiberation(fonts: string, replacement = LIBERATION): void {
  const directory = join(fonts, DIRECTORY);
  const held = existsSync(directory) ? readdirSync(directory) : [];
  if (held.length !== 1 || held[0] !== FILE) {
    throw new Error(
      `Excalidraw's Liberation Sans isn't ${DIRECTORY}/${FILE} alone (${held.join(", ") || "none"}): check which file to replace`,
    );
  }
  cpSync(replacement, join(directory, FILE));
}
