/**
 * What a failure says, as every screen shows it: its message as a sentence of its own, as a reader
 * may see it (lattice issue #552). A refused read's message carries the server's own words, which
 * are shown, as they say what went wrong, but as one line of plain text: no controls, no
 * characters that turn the text's direction or hide in it, and no more than `LONGEST` characters.
 * What was cut or taken out is kept in the console, whole. React writes it as text, so markup in
 * it is shown as written, never run.
 */

/** The most of a failure's message a screen shows. */
export const LONGEST = 200;

/** Controls and format characters: direction marks and overrides, zero-width ones, and the rest. */
const UNSEEN = /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]+/gu;

/** A failure's message, its first letter a capital, for where it starts a sentence. */
export const failureSaid = (error: unknown): string => {
  const whole = error instanceof Error ? error.message : String(error);
  const line = whole.replace(UNSEEN, " ").replace(/\s+/g, " ").trim();
  const chars = [...line];
  const said = chars.length > LONGEST ? `${chars.slice(0, LONGEST - 1).join("")}…` : line;
  if (said !== whole) {
    console.warn("A failure's message, as the server sent it:", whole);
  }
  return said.charAt(0).toUpperCase() + said.slice(1);
};
