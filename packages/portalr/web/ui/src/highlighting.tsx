import type { GrammarState, ThemedToken } from "@shikijs/core";
import { Fragment, type ReactNode, useMemo, useRef } from "react";
import { cn } from "./cn";
import { type Language, languageNamed } from "./languages";
import { useOnDemand } from "./on-demand";
import type { Tokenize } from "./on-demand/highlight";

/** The longest block highlighted; a longer one, which could hold the page, shows as it is. */
const LONGEST = 20_000;

/** Each language's tokenizer, loaded once, the first time a block in it shows. */
const tokenizers = new Map<Language, () => Promise<Tokenize>>();

function tokenizerOf(language: Language): () => Promise<Tokenize> {
  let load = tokenizers.get(language);
  if (!load) {
    load = () => import("./on-demand/highlight").then(({ tokenizer }) => tokenizer(language));
    tokenizers.set(language, load);
  }
  return load;
}

/** A line of a block, by its number, which is its identity: lines are only added after it. */
type Line = { readonly number: number; readonly tokens: ThemedToken[] };

/** The lines a block's code has been tokenized to so far, and where its grammar stood. */
type Done = {
  readonly tokenize: Tokenize;
  readonly code: string;
  readonly lines: readonly Line[];
  readonly after: GrammarState | undefined;
};

/** Shiki's font styles, as bits, and their classes. */
const FONT_STYLES = [
  [1, "italic"],
  [2, "font-semibold"],
  [4, "underline"],
  [8, "line-through"],
] as const;

/** A token of highlighted code, in its colour and its font style. */
export function Token({ token }: { token: ThemedToken }) {
  const style = token.fontStyle ?? 0;
  return (
    // The colour is a custom property's name, which tokens.css sets, given through the CSS object
    // model, as every React style is, which the Content-Security-Policy allows.
    <span
      style={{ color: token.color }}
      className={cn(FONT_STYLES.filter(([bit]) => style & bit).map(([, name]) => name))}
    >
      {token.content}
    </span>
  );
}

/**
 * A block's code, highlighted, or null while its language isn't one `ui` highlights or its grammar
 * is loading. While the fence is still streaming, its whole lines are highlighted as they arrive,
 * each tokenized once, from where the grammar stood after the last, and the line still arriving is
 * shown as it is.
 */
export function useHighlighted(code: string, name: string, complete: boolean): ReactNode {
  const language = languageNamed(name);
  const tokenize = useOnDemand(language && tokenizerOf(language));
  // What is tokenized so far, which the next render of this block goes on from: written during
  // render, as a cache of the code alone, so a render React discards or repeats does no harm.
  const done = useRef<Done | null>(null);
  if (!tokenize || code.length > LONGEST) {
    return null;
  }
  const whole = complete ? code : code.slice(0, code.lastIndexOf("\n") + 1);
  let so = done.current;
  const goesOn =
    so?.tokenize === tokenize &&
    (so.code === whole ||
      ((so.code === "" || so.code.endsWith("\n")) && whole.startsWith(so.code)));
  if (!(so && goesOn)) {
    so = { tokenize, code: "", lines: [], after: undefined };
  }
  if (whole.length > so.code.length) {
    const { lines, after } = tokenize(whole.slice(so.code.length).replace(/\n$/, ""), so.after);
    const from = so.lines.length;
    so = {
      tokenize,
      code: whole,
      lines: [...so.lines, ...lines.map((tokens, at) => ({ number: from + at, tokens }))],
      after,
    };
  }
  done.current = so;
  const arriving = code.slice(whole.length);
  return (
    <>
      {so.lines.map(({ number, tokens }) => (
        <Fragment key={number}>
          {number > 0 && "\n"}
          {tokens.map((token) => (
            <Token key={token.offset} token={token} />
          ))}
        </Fragment>
      ))}
      {so.lines.length > 0 && arriving && "\n"}
      {arriving}
    </>
  );
}

/**
 * Whole code, highlighted line by line, for a view that numbers its lines: each line's tokens, or
 * null while its language isn't one `ui` highlights, its grammar is loading, or the code is longer
 * than is highlighted. Tokenized once for each code.
 */
export function useHighlightedLines(code: string, name: string): readonly ThemedToken[][] | null {
  const language = languageNamed(name);
  const tokenize = useOnDemand(language && tokenizerOf(language));
  return useMemo(
    () => (tokenize && code.length <= LONGEST ? tokenize(code).lines : null),
    [tokenize, code],
  );
}
