/**
 * The languages `ui` highlights, and the names a fence may give each: a short list, each grammar
 * loaded with its first block (portalr ADR-0044). A fence in any other language is shown as it is.
 */

const LANGUAGES = [
  "css",
  "diff",
  "go",
  "html",
  "javascript",
  "json",
  "markdown",
  "python",
  "rust",
  "shellscript",
  "sql",
  "toml",
  "tsx",
  "typescript",
  "yaml",
] as const;

export type Language = (typeof LANGUAGES)[number];

const NAMES: ReadonlyMap<string, Language> = new Map<string, Language>([
  ...LANGUAGES.map((language) => [language, language] as const),
  ["bash", "shellscript"],
  ["cjs", "javascript"],
  ["golang", "go"],
  ["htm", "html"],
  ["js", "javascript"],
  ["jsonc", "json"],
  ["jsx", "tsx"],
  ["md", "markdown"],
  ["mjs", "javascript"],
  ["patch", "diff"],
  ["py", "python"],
  ["rs", "rust"],
  ["sh", "shellscript"],
  ["shell", "shellscript"],
  ["ts", "typescript"],
  ["yml", "yaml"],
  ["zsh", "shellscript"],
]);

/** The language a fence's name is, if `ui` highlights it, in any case. */
export function languageNamed(name: string): Language | undefined {
  return NAMES.get(name.toLowerCase());
}
