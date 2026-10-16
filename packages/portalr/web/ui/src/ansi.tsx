/**
 * A log line with its ANSI colours, and nothing else of its escapes (portalr ADR-0031).
 *
 * A line is text from anywhere. Of what it may carry, only the colour of a character and its
 * bold are taken: the eight foreground colours, and their bright forms as the same colours, in the
 * kit's own palette, which holds its contrast in both schemes. Every other escape sequence, a
 * cursor movement, a clear, a title, a link, a background, a 256-colour or a true colour, is
 * stripped, and so is every control character but a newline and a tab, and every character that
 * changes the direction of text or joins it unseen (bidirectional and other format controls), so
 * a line can't move or overwrite what is around it, reorder it, or send a person anywhere. It is
 * rendered as text, never as markup.
 */

import type { CSSProperties } from "react";

/** A run of text, in a colour of the palette, or none, and bold or not. */
export interface Run {
  /** Where its text begins, among the text of the runs before it: its identity in the line. */
  readonly start: number;
  readonly text: string;
  /** The palette's colour, 0 to 7, or null for the text's own. */
  readonly colour: number | null;
  readonly bold: boolean;
}

/** A character by its code, so the patterns below can name controls that a literal may not. */
const char = (code: number) => String.fromCharCode(code);
const ESC = char(0x1b);
const BEL = char(0x07);
const ST = char(0x9c);
const CSI = char(0x9b);
const OSC = char(0x9d);

/** A range of characters, by their codes, for a pattern's class. */
const range = (from: number, to: number) => `\\u{${from.toString(16)}}-\\u{${to.toString(16)}}`;

/**
 * Either an escape sequence, in one of its forms, or a run of text with none in it. The
 * sequences are matched in one pass without backtracking, so a hostile line is read in time that
 * grows with its length alone; an OSC string's body is bounded, and what is past its bound is text.
 * In order: a CSI sequence (`ESC [` or the C1 form, parameters, intermediates, a final byte), an OSC string (a
 * title, a link, the clipboard) to its bell or its terminator, a device control string and its
 * kin to its terminator, any other escape of a few characters, and, last, plain text.
 */
const TOKEN = new RegExp(
  [
    `(?:${ESC}\\[|${CSI})[${range(0x30, 0x3f)}]*[${range(0x20, 0x2f)}]{0,8}[${range(0x40, 0x7e)}]`,
    `(?:${ESC}\\]|${OSC})[^${BEL}${ESC}${ST}]{0,2048}(?:${BEL}|${ST}|${ESC}\\\\)?`,
    `${ESC}[PX^_][^${ESC}]{0,2048}(?:${ESC}\\\\)?`,
    `${ESC}[${range(0x20, 0x2f)}]{0,8}[${range(0x30, 0x7e)}]?`,
    `[^${ESC}${CSI}${OSC}]+`,
  ].join("|"),
  "gu",
);

/** What an escape sequence begins with: an escape, or the C1 forms of CSI and OSC. */
const INTRODUCERS: ReadonlySet<string> = new Set([ESC, CSI, OSC]);

/** A control or format character other than a newline and a tab, in a run of text. */
const CONTROL = new RegExp(
  `[${[
    range(0x00, 0x08),
    range(0x0b, 0x1f),
    range(0x7f, 0x9f),
    // Format controls: zero-width and direction marks, line and paragraph separators, embeddings
    // and overrides, isolates, invisible operators, the Arabic letter mark and the byte order mark.
    range(0x00ad, 0x00ad),
    range(0x061c, 0x061c),
    range(0x180e, 0x180e),
    range(0x200b, 0x200f),
    range(0x2028, 0x202e),
    range(0x2060, 0x2069),
    range(0xfeff, 0xfeff),
    // Tag characters, which spell text that is not seen.
    range(0xe0000, 0xe007f),
  ].join("")}]`,
  "gu",
);

/** What sets colours and weight: `ESC [`, digits and their separators, and `m`, and nothing more. */
const SGR = new RegExp(`^${ESC}\\[([0-9;:]*)m$`, "u");

/** The line's text in runs, each with the colour and the weight in force where it begins. */
export function runs(line: string): Run[] {
  const found: Run[] = [];
  let colour: number | null = null;
  let bold = false;
  let start = 0;
  for (const each of line.matchAll(TOKEN)) {
    const token = each[0];
    if (!INTRODUCERS.has(token.charAt(0))) {
      const text = token.replace(CONTROL, "");
      if (text !== "") {
        found.push({ start, text, colour, bold });
        start += text.length;
      }
      continue;
    }
    // Only a colour-setting sequence, `ESC [ ... m`, changes how the text that follows looks.
    const params = SGR.exec(token)?.[1];
    if (params === undefined) {
      continue;
    }
    // Parameters are groups split by `;`, and a group's own parts by `:`. A colour with its parts
    // after a colon (`38:2::r:g:b`) is one group; with semicolons (`38;2;r;g;b`), several.
    const groups = (params === "" ? "0" : params).split(";").map((group) => group.split(":"));
    for (let at = 0; at < groups.length; at += 1) {
      const parts = groups[at] ?? [];
      const code = Number(parts[0] || 0);
      if (code === 38 || code === 48 || code === 58) {
        // A 256-colour or a true colour, which the palette has no place for: its arguments go too.
        const kind = parts.length > 1 ? 0 : Number(groups[at + 1]?.[0]);
        at += kind === 5 ? 2 : kind === 2 ? 4 : 0;
      } else if (parts.length > 1) {
        // Anything else with parts after a colon, such as a curly underline, is not a colour.
      } else if (code === 0) {
        colour = null;
        bold = false;
      } else if (code === 1) {
        bold = true;
      } else if (code === 22) {
        bold = false;
      } else if (code >= 30 && code <= 37) {
        colour = code - 30;
      } else if (code >= 90 && code <= 97) {
        colour = code - 90;
      } else if (code === 39) {
        colour = null;
      }
    }
  }
  return found.reduce<Run[]>((merged, each) => {
    const last = merged.at(-1);
    if (last && last.colour === each.colour && last.bold === each.bold) {
      merged[merged.length - 1] = { ...last, text: last.text + each.text };
    } else {
      merged.push(each);
    }
    return merged;
  }, []);
}

/** A line as text in the palette's colours. */
export function AnsiText({ line }: { line: string }) {
  return runs(line).map((each) => {
    const style: CSSProperties | undefined =
      each.colour === null ? undefined : { color: `var(--ansi-${each.colour})` };
    return (
      <span key={each.start} style={style} className={each.bold ? "font-bold" : undefined}>
        {each.text}
      </span>
    );
  });
}
