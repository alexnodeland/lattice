# ADR-0044: Highlighting and math, loaded on demand, each with a size budget of its own

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland
**Amends:** the size budgets of [ADR-0040](0040-scenarios-against-a-generated-application-and-size-budgets.md), and the add-ons of [ADR-0043](0043-markdowns-basics.md)

## Context

[ADR-0043](0043-markdowns-basics.md) gave `Markdown` code blocks of `ui`'s own and an add-ons seam, and held it to the Content-Security-Policy in Chromium. Two add-ons were to follow:

- **Syntax highlighting,** in colours that the tokens, colour-blind mode and forced colours choose.
- **Math,** for the `$$` that models write.

Each is too large for every visit to load. Streamdown's own plugins don't fit: `@streamdown/code` imports every one of Shiki's languages and themes of fixed hex colours, and `@streamdown/math` doesn't expose KaTeX's output. The policy allows no WebAssembly and no inline style, and the size check counted every chunk a build wrote, lazy or not. The math and highlighting below would have taken the app's `total` from 428 kB past its ceiling of 470 kB, to 673 kB, though a visit without a code block or a formula loads none of them.

## Decision

- **Add-ons are modules of `ui/src/on-demand/`,** each imported only when a message needs it, by `useOnDemand`. A module loads once a page, and until it has loaded, or if it can't, what it would draw shows as its source.
- **Highlighting** (`on-demand/highlight.ts`):
  - Shiki's core, with its JavaScript regular expression engine, so nothing compiles WebAssembly.
  - Fifteen languages, each grammar a chunk of its own loaded with its first block: CSS, diff, Go, HTML, JavaScript, JSON, Markdown, Python, Rust, shell, SQL, TOML, TSX, TypeScript and YAML. Their common names are mapped too (`ts`, `py`, `sh`, `yml`, `jsx` as TSX).
  - A block in any other language shows as written.
  - The theme is Shiki's of custom properties (`--code-token-keyword` and the rest), which `tokens.css` sets, with comments in italics too:
    - By default: keywords in the working colour, the other roles in a log line's colours, and comments in the quiet ink.
    - In colour-blind mode: three inks, keywords a blue, strings an orange, the rest the text's own, 20 or more apart, to CIEDE2000, under each deficiency.
    - Under forced colours: the system's colours.
  - Each colour is 4.5:1 or more on the paper and the surface, in both schemes and both modes, which a token test holds.
  - **Streaming:** while a fence is still arriving, its whole lines are highlighted as they come, each tokenized once from where the grammar stood after the last, and the line still arriving shows as it is. A finished block is tokenized once. A colour is given through React's `style`, the CSS object model, which the policy allows.
  - **Bounds:** tokenizing runs as a block renders, so a block over 20,000 characters shows as written, and a line over 1,000 characters is left plain, so that a hostile or minified block can't hold the page.
- **Math:**
  - **Syntax:** `$$…$$` within a line, and a block between `$$` lines, through remark-math with `singleDollarTextMath: false`, so `$5` is a price. A `math` fence is a block too.
  - **Drawing:** Streamdown's math plugin, an object of `ui`'s own (`on-demand/math.ts`). Its rehype step draws each formula with KaTeX as MathML, which Chromium lays out itself, so no stylesheet or typeface comes with it.
  - **Reading untrusted TeX:** `trust: false` (no `\href`, `\url`, `\includegraphics` or `\html…`), sizes and macro expansion bounded, and five thousand characters at most.
  - **Refusals:** KaTeX throws rather than drawing its red error, whose inline style the policy refuses. A formula it can't read stays as its code, which `Markdown` shows as its source with a quiet line, or quietly as text while it is still streaming.
  - **Stripped styles:** KaTeX's MathML has a `style` attribute for `\fcolorbox` and `\pmb` alone, and those are dropped. KaTeX escapes every value and text, so dropping them by pattern is exact.
  - **Placement:** the step runs after the sanitizer, so what it adds must be safe by construction: KaTeX's MathML for TeX read untrusted. A block is a region that scrolls sideways, named "Formula".
  - **Streaming:** `remend` still doesn't close a `$$`.
- **The math switch:** `Addons` gains `math`, on by default. With math off, only the syntax loads (`on-demand/math-syntax.ts`): a block shows as its source with "Math is off here", and a formula within a line as `$$…$$` in code.
- **Budgets** (`scripts/check_size.py`, `size-budget.json`):
  - Vite writes a manifest for each UI, and the wheel leaves it out (`wheel-exclude`), which `check_wheel.py` holds.
  - An add-on is what its module's import reaches, statically or dynamically, that the UI doesn't load without add-ons: what its first use loads. It has a `total` and a `largest` of its own, under the UI's `addons`, and a chunk two add-ons share counts in each (remark-math's, in `math` and `math-syntax`).
  - A UI's `total` and `largest` count only what loads without an add-on, as before for everything else.
  - Every add-on has a budget, and every budget an add-on.
- **The tests:**
  - The CSP tests draw math, on and off, and highlighted code, and the hostile corpus gains TeX that links, loads, styles or recurses.
  - The component tests hold the colours, italics, streaming a line at a time, `$5`, math off, unreadable TeX, and hostile TeX.
  - The screenshots show highlighted code and math in every mode.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Highlighter | **Shiki's core, its JavaScript engine (chosen)** | Grammars as VS Code's; a theme of custom properties; tokens from a grammar's state, a line at a time | 48 kB before a grammar |
| | Shiki with Oniguruma | Every grammar exact | WebAssembly: `'wasm-unsafe-eval'` |
| | lowlight (highlight.js) | Smaller | Classes, not a grammar state to go on from, and a different `code` |
| | `@streamdown/code` | Ready | Every language as a chunk, fixed hex themes |
| Math | **KaTeX as MathML, through Streamdown's plugin slot (chosen)** | One dependency; no stylesheet or face; a screen reader reads MathML | Chromium's MathML look, not KaTeX's |
| | KaTeX as HTML and MathML | KaTeX's look | 3.5 kB of CSS and about 300 kB of typefaces |
| | Temml | Smaller | A second, younger dependency for the same output |
| Budgets | **An add-on's own, from the manifest (chosen)** | A visit's size is what a visit loads; an add-on's growth still fails the check | A manifest per build, left out of the wheel |
| | Raise the UI's `total` | Nothing to build | `total` would stop meaning what loads |

## Consequences

- Easier: code reads in colour in every scheme and mode, and math reads as math, to the eye and to a screen reader, at no cost to a visit without them.
- Harder: a first highlighted block loads about 48 kB, and its grammar from about 1 kB (JSON) to 40 kB (HTML, with CSS and JavaScript); a first formula, 79 kB. Chromium's MathML, unstyled, is plainer than KaTeX's HTML.
- Revisit: a language people ask for, at its grammar's size, and Mermaid's add-on if [ADR-0042](0042-mermaid-cant-draw-under-the-policy.md) is revisited.

### Sizes

The app's are 181.1 / 433.2 / 136.2 kB (initial / total / largest), within its ceilings, which are unchanged. admin holds no add-on. The add-ons, gzipped:

| Add-on | Total | Largest | Ceiling (total / largest) |
|---|---|---|---|
| `highlight`, all fifteen grammars | 160.6 kB | 47.9 kB | 177 / 53 kB |
| `math` | 79.0 kB | 76.9 kB | 87 / 85 kB |
| `math-syntax` | 2.2 kB | 2.1 kB | 2.5 / 2.5 kB |
