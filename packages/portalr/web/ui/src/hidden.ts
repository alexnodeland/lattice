/**
 * What a reader wouldn't see in text, shown: an approval's arguments and a connected app's code
 * are read before they are allowed, so what is read must be what runs.
 */

/** The ranges of characters a reader wouldn't see, as artifactr's scan finds them, kept in step
 * with its `HIDDEN`: controls but tabs and newlines, separators, soft hyphens, zero-width,
 * direction-changing and tag characters, variation selectors, and lone surrogates. */
const HIDDEN: readonly (readonly [number, number])[] = [
  [0x00, 0x08],
  [0x0b, 0x0c],
  [0x0e, 0x1f],
  [0x7f, 0x9f],
  [0xad, 0xad],
  [0x61c, 0x61c],
  [0x180e, 0x180e],
  [0x200b, 0x200f],
  [0x2028, 0x202e],
  [0x2060, 0x2064],
  [0x2066, 0x2069],
  [0xfe00, 0xfe0f],
  [0xfeff, 0xfeff],
  [0xd800, 0xdfff],
  [0xe0000, 0xe007f],
  [0xe0100, 0xe01ef],
];

/** Code with each character a reader wouldn't see shown as its code point, so what is read is
 * what runs; Copy copies it so too. */
export function unhidden(code: string): string {
  let shown = "";
  for (const c of code) {
    const point = c.codePointAt(0) ?? 0;
    const hidden = HIDDEN.some(([low, high]) => point >= low && point <= high);
    shown += hidden ? `\u27e6U+${point.toString(16).toUpperCase().padStart(4, "0")}\u27e7` : c;
  }
  return shown;
}
