/**
 * Highlighting, loaded with the first fenced block in a language `ui` highlights, and each
 * language's grammar with its first block (portalr ADR-0044). Shiki's core, with its JavaScript
 * regular expressions, so nothing compiles WebAssembly; its colours are custom properties
 * (`--code-token-keyword` and the rest), which `tokens.css` sets, so the scheme, colour-blind mode
 * and forced colours choose them.
 */

import {
  createCssVariablesTheme,
  createHighlighterCore,
  type GrammarState,
  type LanguageInput,
  type ThemedToken,
} from "@shikijs/core";
import { createJavaScriptRegexEngine } from "@shikijs/engine-javascript";
import type { Language } from "../languages";

const VARIABLES = createCssVariablesTheme({
  name: "portalr",
  variablePrefix: "--code-",
  fontStyle: true,
});

/** Shiki's theme of custom properties, and comments in italics, a cue beside their colour. */
const THEME = {
  ...VARIABLES,
  tokenColors: [
    ...(VARIABLES.tokenColors ?? []),
    {
      scope: ["comment", "punctuation.definition.comment", "string.quoted.docstring.multi"],
      settings: { foreground: "var(--code-token-comment)", fontStyle: "italic" },
    },
  ],
};

const highlighter = createHighlighterCore({
  themes: [THEME],
  langs: [],
  engine: createJavaScriptRegexEngine(),
});

/** Each language's grammar, a chunk of its own. */
const GRAMMARS: Record<Language, LanguageInput> = {
  css: () => import("@shikijs/langs/css"),
  diff: () => import("@shikijs/langs/diff"),
  go: () => import("@shikijs/langs/go"),
  html: () => import("@shikijs/langs/html"),
  javascript: () => import("@shikijs/langs/javascript"),
  json: () => import("@shikijs/langs/json"),
  markdown: () => import("@shikijs/langs/markdown"),
  python: () => import("@shikijs/langs/python"),
  rust: () => import("@shikijs/langs/rust"),
  shellscript: () => import("@shikijs/langs/shellscript"),
  sql: () => import("@shikijs/langs/sql"),
  toml: () => import("@shikijs/langs/toml"),
  tsx: () => import("@shikijs/langs/tsx"),
  typescript: () => import("@shikijs/langs/typescript"),
  yaml: () => import("@shikijs/langs/yaml"),
};

/** Lines of code as tokens, and where the grammar stood after the last, to go on from there. */
export type Tokens = { readonly lines: ThemedToken[][]; readonly after: GrammarState | undefined };

/** Tokenize whole lines of code, from where an earlier call left the grammar, if one did. */
export type Tokenize = (code: string, after?: GrammarState) => Tokens;

/**
 * How long one line may take, in milliseconds, before Shiki stops it and gives the rest of the
 * line as one plain token, which a block keeps, since it tokenizes each line once (portalr
 * ADR-0044). Shiki's own half a second cut lines on a busy machine; this is a backstop for a
 * grammar's regular expression that runs away, which JavaScript can't otherwise stop, on a
 * render that waits for it. A line is also never longer than `LONGEST_LINE`.
 */
export const LINE_TIME_LIMIT = 5000;

/** The longest line tokenized: a longer one, such as minified code, is shown as it is. */
const LONGEST_LINE = 1000;

/** What a grammar is given once as it loads, so its regular expressions are compiled then. */
const WARM = "a = 1 # x\n";

/** A tokenizer for a language, once its grammar has loaded, and run once to warm it. */
export async function tokenizer(language: Language): Promise<Tokenize> {
  const loaded = await highlighter;
  await loaded.loadLanguage(GRAMMARS[language]);
  const tokenize: Tokenize = (code, after) => {
    const { tokens, grammarState } = loaded.codeToTokens(code, {
      lang: language,
      theme: THEME,
      tokenizeMaxLineLength: LONGEST_LINE,
      tokenizeTimeLimit: LINE_TIME_LIMIT,
      ...(after && { grammarState: after }),
    });
    return { lines: tokens, after: grammarState };
  };
  // The grammar's first, cold run compiles its expressions: done here, where nothing is kept, so
  // no block's line pays for it.
  tokenize(WARM);
  return tokenize;
}
