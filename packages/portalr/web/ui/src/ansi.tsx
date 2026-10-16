/**
 * A log line with its ANSI colours, and nothing else of its escapes (portalr ADR-0031).
 *
 * A line is text from anywhere. Of what it may carry, only the colour of a character and its
 * bold are taken: the eight foreground colours, and their bright forms as the same colours, in the
 * kit's own palette, which holds its contrast in both schemes. Every other escape sequence, a
 * cursor movement, a clear, a title, a link, a background, a 256-colour or a true colour, is
 * stripped, and so is every control character but a newline and a tab, so a line can't move or
 * overwrite what is around it, or send a person anywhere. It is rendered as text, never as markup.
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

/** A range of characters, by their codes, for a pattern's class. */
const range = (from: number, to: number) => `\\u{${from.toString(16)}}-\\u{${to.toString(16)}}`;

/**
 * Either an escape sequence, in one of its forms, or a run of text with none in it. The
 * sequences are bounded, so a hostile line is read in time that grows with its length alone.
 * In order: a CSI sequence (`ESC [`, parameters, intermediates, a final byte), an OSC string (a
 * title, a link, the clipboard) to its bell or its terminator, a device control string and its
 * kin to its terminator, any other escape of a few characters, and, last, plain text.
 */
const TOKEN = new RegExp(
  [
    `${ESC}\\[([${range(0x30, 0x3f)}]{0,64})[${range(0x20, 0x2f)}]{0,8}[${range(0x40, 0x7e)}]`,
    `${ESC}\\][^${BEL}${ESC}]{0,2048}(?:${BEL}|${ESC}\\\\)?`,
    `${ESC}[PX^_][^${ESC}]{0,2048}(?:${ESC}\\\\)?`,
    `${ESC}[${range(0x20, 0x2f)}]{0,8}[${range(0x30, 0x7e)}]?`,
    `[^${ESC}]+`,
  ].join("|"),
  "gu",
);

/** A control character other than a newline and a tab, in a run of text. */
const CONTROL = new RegExp(`[${range(0x00, 0x08)}${range(0x0b, 0x1f)}${range(0x7f, 0x9f)}]`, "gu");

/** What sets colours and weight: parameters of digits, and the separators between them. */
const SGR = /^[0-9;:]*$/u;

/** The line's text in runs, each with the colour and the weight in force where it begins. */
export function runs(line: string): Run[] {
  const found: Run[] = [];
  let colour: number | null = null;
  let bold = false;
  let start = 0;
  for (const each of line.matchAll(TOKEN)) {
    const token = each[0];
    const params = each[1];
    if (!token.startsWith(ESC)) {
      const text = token.replace(CONTROL, "");
      if (text !== "") {
        found.push({ start, text, colour, bold });
        start += text.length;
      }
      continue;
    }
    // Only a colour-setting sequence, `ESC [ ... m`, changes how the text that follows looks.
    if (
      params === undefined ||
      !SGR.test(params) ||
      !token.endsWith("m") ||
      !token.startsWith(`${ESC}[`)
    ) {
      continue;
    }
    const codes = (params === "" ? "0" : params).split(/[;:]/).map((code) => Number(code || 0));
    for (let at = 0; at < codes.length; at += 1) {
      const code = codes[at] ?? 0;
      if (code === 0) {
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
      } else if (code === 38 || code === 48 || code === 58) {
        // A 256-colour or a true colour, which the palette has no place for: its arguments go too.
        at += codes[at + 1] === 5 ? 2 : codes[at + 1] === 2 ? 4 : 0;
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
