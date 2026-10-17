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

/** A tokenizer for a language, once its grammar has loaded. */
export async function tokenizer(language: Language): Promise<Tokenize> {
  const loaded = await highlighter;
  await loaded.loadLanguage(GRAMMARS[language]);
  return (code, after) => {
    const { tokens, grammarState } = loaded.codeToTokens(code, {
      lang: language,
      theme: THEME,
      // A longer line, such as minified code, is shown as it is, rather than holding the page.
      tokenizeMaxLineLength: 1000,
      ...(after && { grammarState: after }),
    });
    return { lines: tokens, after: grammarState };
  };
}
