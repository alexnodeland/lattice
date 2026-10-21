# RFC-0007: portalr brand kits

**Status:** Draft
**Author:** Alex Nodeland
**Created:** 2026-10-20
**Discussion:** the pull request that adds this file

## Summary

A deployment of portalr can be restyled by plugging in a brand kit: a folder holding `brand.json` (identity, copy, assets, font licences) and two token files in the W3C Design Tokens (DTCG) format, `tokens.light.json` and `tokens.dark.json`. A kit is a delta over portalr's default kit: it names only what it changes. portalr validates the kit in Python, compiles it to one stylesheet, `brand.css`, serves it under a content hash, and rewrites the UIs' `index.html` at serve time so the kit's title, icon and stylesheet are in place before the first paint. The kit overrides tokens and nothing else: three layers of them (primitives, semantic roles, and a full inventory of component tokens), including a motion system with guard rails. The default look becomes a kit of its own, `brand/default`, from which a generated stylesheet replaces today's hand-written `tokens.css` with every computed value unchanged. A kit is chosen per deployment; per tenant comes later, and the seams for it are named below.

## Motivation

A team that deploys lattice wants the portal to look like theirs: their name in the tab, their mark in the header, their colours, type, corners, shadows and motion. Today the look is portalr's own (lattice ADR-0014, portalr ADR-0019, 0029, 0036, 0037, 0039), held in one hand-written `tokens.css` of semantic roles. Restyling means forking it, and the components still carry spacing, radii, shadows and durations of their own in their class strings, so a fork reaches only the colours.

The UI audit of 2026-10-20 found the same faults from the other side: 13 link styles and 12 button styles, ad hoc heading sizes, raw `a`, `button`, `details` and `ins` elements with the browser's own focus ring, and no `::selection` or scrollbar styling. A kit that can restyle every component needs every component to read its look from tokens; a polish pass that standardises the components needs the same. This RFC does both in one order of work.

Why now: v0.2 is the release a team first deploys, and the polish PRs are about to touch every class string. Laying the token layers down first means each polish PR lands on tokens, not on literals.

## Design

### Scope and the owner's decisions

Decided by the owner, before this RFC and on its pull request, and recorded here:

- **Format:** `brand.json` plus DTCG tokens, `tokens.light.json` and `tokens.dark.json`, with aliases and typed validation.
- **Override layer:** tokens only in v0.2. No `parts.css` or other free-form CSS; a free-form layer may be proposed for v0.3, with its own review.
- **Depth:** the full component-token inventory and a motion system.
- **Scope:** per deployment. Per tenant later; the layout stays additive so it can come without a break.
- **The default marks are fully replaceable.** portalr's and grantr's marks and the lattice inks (lattice ADR-0001, ADR-0014) ship with the code under MIT, with a trademark note: the marks stay lattice's trademark and are not licensed for reuse as someone else's product, but a kit may remove or replace them. No separate licence, and no attribution is required.
- **`tokens.dark.json` holds only what differs** from the light scheme.
- **A kit's fonts are not shared with mini apps** until v0.3.
- **The style census reports** in the foundation PR and fails the build once the polish PRs have landed. The Biome raw-element rule and the literal-value test fail the build from the start.

### The kit's files

```
brand/<name>/
  brand.json            identity, copy, assets, fonts and their licences, presets
  tokens.light.json     DTCG tokens: what this kit changes from the default, in light
  tokens.dark.json      DTCG tokens: what differs in dark from this kit's light
  NOTICE                written by `portalr brand init`: what the kit carries, under what terms
  assets/
    mark-light.svg      the header mark, per scheme
    mark-dark.svg
    favicon.svg         and optional favicon-32.png, apple-touch-icon.png
  fonts/
    <family>-<axis>.woff2
    LICENSE-<family>.txt
```

`brand.json`:

```json
{
  "$schema": "https://lattice.dev/schemas/portalr-brand-1.json",
  "version": 1,
  "name": "nightshade",
  "identity": { "product": "Nightshade", "app": "Nightshade", "admin": "Nightshade admin" },
  "copy": { "tagline": "Ask, and it is drafted.", "signIn": "Sign in to Nightshade" },
  "assets": {
    "mark": { "light": "assets/mark-light.svg", "dark": "assets/mark-dark.svg" },
    "favicon": "assets/favicon.svg"
  },
  "fonts": [
    {
      "family": "Inter",
      "role": "sans",
      "files": [{ "path": "fonts/inter-wght.woff2", "weight": "100 900", "style": "normal", "unicodeRange": "U+0000-00FF" }],
      "licence": { "spdx": "OFL-1.1", "file": "fonts/LICENSE-inter.txt" }
    }
  ],
  "presets": { "shape": "soft", "motion": "subtle", "elevation": "shadow" }
}
```

The `$schema` URL is a placeholder: no domain is claimed for it yet. `version` is the version of the token inventory the kit was written against (see "Kit versions"). Copy keys are a closed set the UIs read; an unknown key is an error. Every string in `identity` and `copy` is text, never markup: the loader rejects control characters, bidi overrides and newlines, caps each length (identity names 64 characters, copy 200), and HTML-escapes every string it writes into a page.

### A kit is a delta

A kit names only the tokens it changes. The loader builds the token set as a cascade: the default kit's tokens, then the presets the kit names, then the kit's own `tokens.light.json`, then, for dark, `tokens.dark.json` laid over the result for light. A token the kit doesn't name keeps its default. `portalr brand init` writes the default kit's full token set into the new kit as `tokens.reference.json`, which the loader ignores, so every token can be found without reading portalr's source.

**Kit versions.** The inventory is frozen when the foundation PR merges, as version 1. A token added later is added with a default and a bump of the inventory version; a kit written for version 1 keeps working, since the new token takes its default. A token renamed or removed is a major bump, and the loader names the kit's stale paths.

### Light and dark

Both schemes are resolved separately: light is default, presets, `tokens.light.json`; dark is that same result with `tokens.dark.json` laid over it. Aliases resolve after the layering, within each scheme, so `{color.accent}` in dark resolves to the dark accent. A token that appears only in `tokens.dark.json` overrides only dark; it must still be a path in the inventory.

Emission, for any `$type`:

- A token whose resolved value is the same in both schemes is emitted once.
- A colour that differs is emitted as one `light-dark()` pair, as `tokens.css` does today.
- Any other token that differs (a shadow, whose colour and alpha differ by scheme; `--scrim`; a dimension) is emitted with `light-dark()` per colour inside the value where only its colours differ, and otherwise twice: once in `:root`, once in a dark block that mirrors how a scheme is chosen today (`:root[data-theme="dark"]`, and `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }`). `scheme.js` is unchanged.

### Three token layers

Each layer is a set of CSS custom properties on `:root`. A layer reads only the layers beneath it, so a kit can change a primitive and see every role and component follow, or pin one component token alone.

1. **Primitives:** colour ramps and the inks; `--space-*`; `--radius-0` to `--radius-4`; `--font-size-*`, `--leading-*`, `--weight-*`; `--shadow-1` to `--shadow-4`; `--border-width-*`; `--duration-*`; `--ease-*`.
2. **Semantic roles:** today's names, unchanged: `--paper`, `--surface`, `--fg`, `--muted`, `--line`, `--edge`, `--accent`, `--on-accent`, `--focus`, `--danger`, `--status-*`, `--chart-*`, `--ansi-*`, `--code-token-*`, `--page-width`, `--row-height`, `--scrim`, `--shadow-color`.
3. **Component tokens,** each defaulting to a role or a primitive: `--button-radius`, `--button-pad-x`, `--button-pad-y`, `--button-weight`, `--button-shadow`, `--button-lift`, `--button-press-scale`; input, select, checkbox and switch; card; dialog (scrim blur, width, enter and exit); menu, popover and tooltip; tabs; badge; table; nav, sidebar and header; toast; chat bubbles, tool rows, question cards and the inline artifact's chrome; code block; plus focus ring, scrollbar, selection and icon stroke. A component's styles read its component tokens; those default to roles and primitives, so a component reaches the lower layers only through its own tokens.

Every token today's `tokens.css` and `styles.css` declare keeps its name and its computed value. `tokens.css` has about 84 declarations today; the full inventory is estimated at 300 to 400.

**Derived colours are generated, not written.** `--danger-hover`, `--wash`, `--accent-hover` and `--chart-grid` are `color-mix()` today. The loader computes each from its inputs (the same mix, done in Python) and emits a colour; a kit can't set them directly. Their pairs are in the contrast set. The literal-value guard rail exempts the generated `brand.css`, and `tokens.css` while it remains.

### DTCG mapping

The loader targets DTCG format module draft 2025.10, with a documented profile:

- `color`: a hex string (`#rrggbb`, or `#rrggbbaa` on the tokens listed as taking alpha: `--scrim`, `--shadow-color`, `--chart-grid`'s inputs) or an `oklch()` string; out-of-gamut `oklch()` is mapped to sRGB by chroma reduction before checks and emission. No named colours, `rgb()`, `hsl()` or `color-mix()`.
- `dimension`: `rem` or `px`, a number in a per-token range; no `em`, `%`, `vh` or `vw`.
- `duration`: `ms`, 0 to 600.
- `cubicBezier`: four numbers, x in 0..1, y in a range set by the overshoot rail.
- `fontFamily`: a list of family names, each letters, digits, spaces and hyphens only (no quotes, backslashes or semicolons), ending in a generic from an allow-list (`ui-sans-serif`, `system-ui`, `sans-serif`, `ui-serif`, `serif`, `ui-monospace`, `monospace`). The loader quotes the names it prints.
- `fontWeight`: 100 to 900. `number`: per-token range.
- `shadow`: a DTCG shadow or list of them, each of dimensions and a colour.

The mapping from a token's path to its custom property is a **lookup table** in the loader, one row per token, not a prefix rule. A path with no row is an error. Some rows:

| DTCG path | `$type` | CSS custom property | Example value |
|---|---|---|---|
| `color.ink.portalr.cyan` | `color` | `--portalr-cyan` | `#009fe3` |
| `color.ink.portalr.violet` | `color` | `--portalr-violet` | `#6b2fa0` |
| `color.ramp.violet.700` | `color` | `--color-violet-700` | `#6b2fa0` |
| `color.paper` | `color` | `--paper` | `{color.ramp.violet.50}` |
| `color.status.failed` | `color` | `--status-failed` | `#8a0f2c` |
| `color.chart.1` | `color` | `--chart-1` | `{color.ramp.violet.700}` |
| `space.3` | `dimension` | `--space-3` | `{ "value": 0.75, "unit": "rem" }` |
| `radius.2` | `dimension` | `--radius-2` | `{ "value": 0.375, "unit": "rem" }` |
| `font.family.sans` | `fontFamily` | `--font-sans` | `["Inter", "ui-sans-serif"]` |
| `font.size.body` | `dimension` | `--font-size-body` | `{ "value": 0.875, "unit": "rem" }` |
| `font.weight.strong` | `fontWeight` | `--weight-strong` | `600` |
| `font.leading.body` | `number` | `--leading-body` | `1.5` |
| `shadow.2` | `shadow` | `--shadow-2` | a DTCG shadow object, layers allowed |
| `border.width.1` | `dimension` | `--border-width-1` | `{ "value": 1, "unit": "px" }` |
| `motion.duration.fast` | `duration` | `--duration-fast` | `{ "value": 120, "unit": "ms" }` |
| `motion.ease.out` | `cubicBezier` | `--ease-out` | `[0.2, 0, 0, 1]` |
| `component.button.radius` | `dimension` | `--button-radius` | `{radius.2}` |
| `component.dialog.enter` | extension | `--dialog-enter-duration`, `-ease`, `-opacity`, `-shift`, `-scale` | `"rise"` |

Aliases: `{path}` resolves in the loader. A token without `$type` takes its row's type; an alias must resolve to a token of the same type, except that a `number` row may not alias a `dimension` or the reverse. Alias chains are at most 8 deep; a cycle, an unknown path, or a type mismatch is an error.

**Motion patterns are not DTCG.** DTCG's `transition` composite doesn't describe an entry pattern, so `component.*.enter` and `component.*.exit` take a loader-owned string enum (`none`, `fade`, `rise`, `scale`, `slide-start`, `slide-end`, `slide-up`, `slide-down`) under `$extensions["dev.lattice.portalr"].pattern`. The loader expands a pattern into the five custom properties in the last row, from the motion scales and the preset.

The inks of lattice's other packages (grantr's gold among them) stay in the default kit under `color.ink.<package>.*`. Today grantr's screens re-skin the accent with `[data-brand="grantr"]`; under a kit, that block is part of the default kit's emission and a kit's accent applies to grantr's screens too, unless the kit sets `color.ink.grantr.*`.

### Validation

All of it in Python, in the loader, before anything is served; `portalr brand validate` runs the same code. No text a kit wrote reaches `brand.css`: the loader prints values it built from the parsed grammar, and font family names, which it quotes after the character check above.

- **A checked-in pair manifest,** `packages/portalr/brand/pairs.json`: each entry a foreground token, a background token, a minimum ratio, and the schemes it holds in. The Python validator and the UI's token tests read the same file. Alpha tokens are composited over a named backdrop (`--paper` unless the entry names another) before a ratio is taken. The set: text on paper, surface and wash at 4.5:1; `--muted` likewise; `--on-accent` on `--accent` and `--accent-hover`; `--on-danger` on `--danger` and `--danger-hover`; control edges, status marks and chart marks at 3:1 on paper and surface; ANSI and code tokens at 4.5:1; disabled text and placeholders at 3:1 (WCAG exempts disabled controls; this floor is ours); and the chrome pairs below.
- **Colour-vision distances,** using Machado et al. (2009) at severity 1.0 for protanopia, deuteranopia and tritanopia, plus normal vision: the three chart colours pairwise, each against `--status-failed` and `--status-warn`, and the two status colours against each other, 20 or more apart to CIEDE2000 (portalr ADR-0039). The ANSI colours are held to contrast only, not to distance, which across eight colours could not be met.
- **Accessibility floors on tokens:** the focus ring at least 2px wide with an offset of at least 2px, and 3:1 against both the element and the surface around it; a minimum target of 24 by 24 CSS pixels, held on `--row-height`, the button and icon-button paddings and sizes; body text at least 14px with leading at least 1.4; and under the `flat` elevation preset, controls keep a border of at least 1px in `--edge`.
  - **Admin's compact density is a deliberate exception** (owner's decision): its 13px table text and tighter rows (portalr ADR-0039) are exempt from the 14px text and 24px target floors, which hold for the app people use. A kit can't shrink the compact density further: its tokens (`--row-height`, `--row-pad`, `--table-text` under `[data-density="compact"]`) are in base.css, outside the kit's grammar.
- **Assets:** SVG by an allow-list of elements and attributes. Refused: `script`, `foreignObject`, `style` elements and attributes, `use`, `image`, event handlers, `href` and `xlink:href` to anything but a fragment in the same file, `url()` to anything but a fragment, a DOCTYPE or entity declaration, and `data:` URLs. 64 KB per SVG. PNG favicons are checked by magic number, 128 KB each.
- **Fonts:** WOFF2 only, checked by its magic number (`wOF2`), 400 KB per file and 1.5 MB per kit; every family has a licence entry with an SPDX id from an allowed list (OFL-1.1, Apache-2.0, MIT, or `LicenseRef-commercial` with its file). The licence is the kit author's attestation: the validator checks that it is declared and present, not that it is true.
- **Motion guard rails,** below.

A bad kit fails the application's start with every fault listed.

### Motion

A closed set of entry and exit patterns (above), a duration scale and an easing scale, and three presets (`none`, `subtle`, `lively`). The validator holds:

- **Durations:** no transition or animation token over 600ms. Tokens marked instant (hover and press feedback) at 80ms or less.
- **Flashing:** no looping animation with a period under 333ms (three a second) whose opacity or luminance changes by more than 10%. The only looping animation in the inventory is the placeholder pulse.
- **Shift:** `*-shift`, `*-lift` and slide distances at most 24px.
- **Scale:** `*-scale` entry values from 0.9 to 1; `--button-press-scale` from 0.95 to 1.
- **Overshoot:** an easing curve's y values between -0.1 and 1.1.

**Reduced motion is structural.** Every component's motion reads its duration through `calc(var(--x-duration) * var(--motion-scale))`, and its shift and scale likewise against `--motion-scale`. The base stylesheet, after `brand.css`, sets under `prefers-reduced-motion: reduce`:

```css
@media (prefers-reduced-motion: reduce) {
  :root { --motion-scale: 0 !important; --motion-loop: paused !important; }
}
```

`--motion-scale` and `--motion-loop` are not in the kit's grammar. Infinite animations (the pulse) read `animation-play-state: var(--motion-loop)` and stop at rest, at their resting opacity (the placeholder at its resting opacity). Motion driven from script reads the same media query and tokens. A test renders a worst-case kit (every duration at 600ms, the `lively` preset) under reduced motion and asserts every computed `transition-duration` and `animation-duration` is 0s or the animation is paused at its still state. A kit that wants no motion at all takes the `none` preset.

### What a kit can't brand

The security chrome stays portalr's: the mini app's label and frame (portalr ADR-0051), host dialogs, the skip link, the colour-blind patterns (ADR-0036) and the forced-colours styles.

- The chrome reads only a small pinned set of chrome tokens (`--chrome-fg`, `--chrome-bg`, `--chrome-edge`, `--chrome-focus`), outside the kit's grammar. They are derived from the kit's validated `--fg`, `--surface`, `--edge` and `--focus`, and fall back to the default kit's values for any of them that fails its chrome pair.
- The pair manifest names the chrome's pairs explicitly: label text on its background at 4.5:1, its edge at 3:1 against its background and against the kit's `--paper` and `--surface`, so the chrome is told from the kit's surfaces around it.
- `brand.css` never sets `color-scheme` or `forced-color-adjust`, and contains no `@import` and no `url()` but the loader's own `@font-face` sources. It is linked before the base stylesheet, so the base's forced-colours and reduced-motion blocks win.
- App frame sizing and the mini-app bridge are untouched. Mini apps get the kit's resolved colours through `window.host` (portalr ADR-0051), and not its fonts.

### Presets

`brand.json` names a preset per axis, which sets a group of primitives and component tokens between the default and the kit's own tokens: shape (`sharp`, `soft`, `round`), motion (`none`, `subtle`, `lively`), elevation (`shadow`, `border`, `flat`). The defaults (`soft`, `subtle`, `shadow`) are today's look.

### Loading and serving

- `Site(brand=...)`, a path to the kit's folder (or None for the default), validated when the application starts. Rolling out a changed kit is a restart; a tab open on the old hash keeps its stylesheet, which stays served for the life of the process that compiled it, and takes the new one on its next load.
- The **content hash** covers the compiled `brand.css`, every asset and font file, and the `config.json` brand block.
- `config.json` gains a `brand` block: the kit's hash, identity, copy, and the hashed URLs of the stylesheet and assets.
- Served at `/portalr/brand/<hash>/<path>`, only for paths in the compiled manifest; anything else is 404. Each response has an explicit `Content-Type`, `X-Content-Type-Options: nosniff`, and `Cache-Control: public, max-age=31536000, immutable`. SVGs also carry `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox`.
- **The header mark is an `<img>`,** never inlined SVG.
- **Fonts** are emitted as `@font-face` rules with the hashed URL, `font-display: swap`, the file's weight and style, and its `unicode-range` when the kit gives one.
- The UIs' `index.html` is rewritten at serve time: `<title>`, the icon links, `theme-color` meta (one per scheme, with `media="(prefers-color-scheme: …)"`, from the resolved `--paper`), and a `<link rel="stylesheet">` to `brand.css` before the base stylesheet. Every inserted string is HTML-escaped. The rewritten page is served `Cache-Control: no-cache` with an `ETag`, never immutable. `scheme.js` stays as it is.
- The stackr template takes `PORTAL_BRAND_DIR`.
- A `portalr brand` CLI: `init` (a new kit from the default, with a preset, a `NOTICE`, and the reference token file), `validate`, and `preview` (the component matrix and motion playground against the kit).

### The default kit

`brand/default` holds today's look, its colours in hex as today. A generated stylesheet replaces the hand-written `tokens.css`: it will not match today's file byte for byte (comments, the order of blocks, the derived `color-mix()` values computed, the `[data-brand]`, system-colour and forced-colours blocks moved to the base stylesheet), so the claim is two separate ones:

- **The generated file** is checked in, and a test regenerates it from `brand/default` and fails on any diff. The generator is the Python loader, run by `make brand` and in that test; the UI build reads the checked-in file and needs no Python.
- **Every computed value is unchanged.** Computed-style snapshots per component, in its rest, hover, focus-visible, active and disabled states, in light, dark, forced colours and reduced motion, including the `transition-*` and `animation-*` properties, are taken before the refactor and held after it. And the existing screenshot baselines must not move.

When a literal moves to `var()`, its unit is kept (`0.375rem` stays `rem`, `1px` stays `px`), so a computed value can't drift by rounding.

### Fixtures

Two example kits: `nightshade`, an ordinary one, and `calm`, an extreme one (`round`, `none`, `flat`, a different face) that proves the layers reach every component. The component matrix and the motion playground are screenshot fixtures in the vitest browser suites. To bound their cost, the full matrix runs against the default kit in both schemes; `nightshade` and `calm` run a reduced matrix (one of each component, both schemes), about 60 screenshots in all.

### Guard rails for the components

From the audit, enforced in CI so the components stay on tokens: Biome's `noRestrictedElements` for raw `a`, `button`, `table`, `select`, `details`, `summary` and `ins` outside the kit's own components, and a test that refuses hex, `rgb()`, arbitrary px or rem values and `color-mix()` outside the generated token stylesheet and `styles.css`: both fail the build from the foundation PR on. A style-census test in the screenshot suites counts distinct link, button and heading styles, and reports until the polish PRs have landed, then fails the build.

### Per tenant, later

What holds now so per tenant can come without a break: `config.json`'s brand block is keyed by the kit's hash; `Site(brand=...)` will also accept a resolver from the request to a kit; brand URLs already carry the hash, so several kits can be served side by side; and the rewritten `index.html` will gain `Vary` on whatever selects the tenant. None of this is built in v0.2.

### Print and export

Printing uses the light scheme's resolved tokens. A chart exported as an image takes the kit's chart colours and the default fonts, since kit fonts are not embedded in exports in v0.2.

### Staging

Each step is one PR, reviewable alone.

0. **Docs:** this RFC, portalr ADR-0056 (token layers, loading, validation) and ADR-0057 (motion, and tokens as the only override).
1. **Foundation:** primitives, radius, shadow and motion tokens at today's computed values; the component tokens, one component per commit, with the computed-style snapshots; the structural reduced-motion block; the guard rails. Zero screenshot baseline diffs. It starts when nothing open touches `styles.css`, `tokens.css` or a component's class strings at the time of its rebase: today that means #428, #434, #435 and the merge-queue PRs that carry them (#441), and #431, now merged. The token inventory is frozen at its merge as version 1.
2. **Loader:** depends on the foundation's inventory. `brand.json` and DTCG parsing, the pair manifest, validation, `brand.css`, `Site(brand=...)`, serving, the `index.html` rewrite, `config.json`'s block, and `nightshade`. Can run in parallel with the polish PRs.
3. **CLI and kit tooling:** `portalr brand init/validate/preview`, the component matrix and motion playground, presets, the stackr template's `brand/` and `PORTAL_BRAND_DIR`, the docs, and `calm`.

The polish PRs, approved by the owner (links and breadcrumbs, list rows, icon buttons and the inline artifact header, badges and headings, disclosures, the shell, empty and error states), follow the foundation and land on its tokens.

## Foundation PR as built

The foundation PR (#452) departs from the design above in these ways, each reviewed there:

- **Derived colours stay `color-mix()`** in `base.css`: `--wash`, `--accent-hover`, `--danger-hover`, `--danger-wash` and `--chart-grid`. Computing them in Python risks a rounding difference from the browser's own mix, and `--wash` and `--accent-hover` are declared again under `[data-brand]`, where the accent changes. The loader PR computes them for a kit other than the default, and holds their pairs.
- **The literal-value guard rail** exempts `tokens.css`, `base.css` and `styles.css`, not only the generated stylesheet. A few layout measures remain, listed in the test by count, including the editor's and the mini apps' frame heights, which stay as they are.
- **The scales are as wide as today's values:** corners `--radius-0` to `--radius-6` and `--radius-full`, and shadows `--shadow-1` to `--shadow-3`, since a zero-change refactor can't snap a value to a nearer step. Tailwind's spacing utilities (`p-3`, `gap-2`) keep Tailwind's `--spacing` and are not on the `--space-*` scale; a component's token is.
- **Motion's scale multiplies durations only.** Shifts and scale offsets are not multiplied: with every duration 0 they move nothing. Every duration token is declared on the root, where `--motion-scale` is already 0 under reduced motion, so an element can't undo it below, and no kit can declare `--motion-scale` or `--motion-loop`, which the tests hold.
- **Not tokens yet:** `--button-shadow`, `--button-lift` and `--button-press-scale`, which have no value today; adding them changes a computed value. The polish pass adds them where a look needs them.
- **Some component tokens are literals,** not primitives: `--dialog-pad`, `--dialog-scrim-blur`, `--segmented-item-pad-x`, `--popover-item-pad-x`, `--switch-width`, `--switch-height` and `--focus-offset`, as no primitive has their value. `--switch-thumb` and `--switch-travel` are separate tokens: a kit that changes one changes the other, which the loader PR checks.
- **Colour ramps** come with the loader PR.
- **The reduced-motion test** lays the generated stylesheet, every duration at 600ms, over the default, and opens a dialog, a menu, a select's list and the drawer; the guard rails' validation of a kit's motion is the loader PR's.
- **Sizes** are read where a size token sets a box's width or height (the dialog's width and margin, the drawer's width, the switch, the checkbox, the progress bar and a row's height) and the enter and exit scales, by `token-sizes.test.tsx`; corners and padding are read by the computed-style snapshots; every other size by the screenshot suites; the computed-style snapshots read what a declaration sets and leave sizes, margins and transforms out.
- **The style census** reports in the test's annotations, not yet in the CI step summary.

## Loader PR as built

The loader PR departs from or defers parts of the design above:

- **`brand.css` comes after the UI's own stylesheet**, not before base.css as written above: before it, the UI's generated `tokens.css` would undo the kit. Where base.css declares a token again under a selector, it must still win: admin's density is declared on an element below the root, so it does; colour-blind mode is declared on the root, so a kit declares what that mode swaps (the chart series and code's colours) under `:root:not([data-cvd])`, and the mode's palette wins where it is asked for. The reduced-motion block wins by `!important`, as designed. A test holds that the swapped set is base.css's.
- **Derived colours stay `color-mix()` in base.css.** The validator mixes `--wash`, `--accent-hover`, `--danger-hover` and `--danger-wash` the same way in Python (sRGB, at base.css's shares) to hold their pairs, so a kit's colours are checked as the page draws them.
- **The pair manifest** is `src/portalr/brand/pairs.json`: 70 pairs, each with its floor, why, and, where a colour is clear, the backdrop it is drawn over (the paper unless named). Status colours are held as marks (3:1), since the badges' words are in the ink. The UI's token tests still hold the default kit by their own list; moving them onto the manifest is a follow-up.
- **Colour-vision distances** are held for two sets, as the default's tests hold them: the three chart series, and the two status colours with the chart's teal.
- **Floors are held in both schemes.**
- **Marks** are held to an allow-list by namespaced name: an `<svg>` in the SVG namespace, no attribute in another namespace, UTF-8 with no byte-order mark, nothing declared (no DOCTYPE, entity, CDATA or processing instruction but the XML declaration), no backslash in an attribute, and a `url()` only to a fragment of the mark. Every served file's suffix is one the portal has a type for, judged by the file a link resolves to.
- **Faces** are checked by their WOFF2 header (signature, length, tables, size), not parsed: the browser's own sanitiser (OTS) is the real defence against a malformed font. `LicenseRef-commercial` admits any commercial licence with its text, so the licence check is an attestation, not a gate. A licence is a `.txt` file of 64 KB at most, counted in the faces' budget; a kit brings 16 face files at most; `brand.json` and the token files are 256 KB at most and the kit's own, not links.
- **The index** is read and branded once, as the application starts; a build with no `<title>` or no `</head>` fails the start, as a kit with a fault does. The name is HTML-escaped and placed as text. The page carries an ETag and answers `If-None-Match` with 304.
- **Not yet:** the pinned chrome tokens (`--chrome-*`), so the skip link and the mini app's chrome still read the kit's roles, held by the same pairs; presets (`brand.json` refuses a `presets` key until they exist); an `oklch()` colour; an "instant" duration class; and the stackr template's `PORTAL_BRAND_DIR`, with the CLI.
- **Nothing in the UIs reads `config.json`'s brand block yet.** The tab's title and icon and the kit's look come from the rewritten index and `brand.css`; the header's mark, the product's name in the header, the tagline and the sign-in words have no visible effect until the follow-up PR that reads them, which comes before the CLI PR.
- **A kit is read when the `Site` is made,** at the application's start: `Site(brand=Path(...))`, and `site.kit` is the kit, read. Its files are served at `/portalr/brand/<hash>/`, the hash over every file and `brand.json`.
- **A kit's version** must be the inventory's, 1; when a later inventory comes, a version-1 kit keeps working by the defaults of what it doesn't name, and the loader will accept it.

## Drawbacks

- Hundreds of custom properties, and a refactor that touches every component. The zero-diff gate and the per-component commits are what make it reviewable.
- A token-only kit can't change a layout or a component's shape beyond what its tokens reach. That is the point in v0.2, and the reason for the full inventory.
- Validation in Python means the browser trusts the compiled `brand.css`; the type grammar is the one place it must be right.
- A content hash in a URL and an `index.html` rewritten at serve time are two more things to cache correctly.
- Kits must be upgraded as the inventory grows. Defaults make additions free; renames are a major version.
- Screenshots grow by about 60 for the fixtures.

## Alternatives

- **A `parts.css` override** of free-form CSS: reaches anything, but can break the security chrome and every screenshot, and can't be validated. Not in v0.2 (owner's decision).
- **A complete kit** rather than a delta: every kit restates hundreds of tokens and breaks when one is added.
- **A theme in TypeScript,** compiled into the bundle: a kit would need a build per deployment. The same UIs serving every deployment is a rule of `Site` today.
- **Style Dictionary or another token compiler** in the build: a Node dependency for a Python service, and it validates no contrast. The mapping table is small enough to own.
- **Tokens as YAML or a flat CSS file:** no aliases or types (YAML), or nothing to validate (CSS). DTCG is a standard other tools export.
- **Per tenant now:** needs the kit in the database and a stylesheet per request. The seams are named above (owner's decision).

## Unresolved questions

- The final URL for `brand.json`'s schema.
- The exact component token names, settled component by component in the foundation PR.
- Whether `lively` earns its place once the motion playground shows it.
- How the generated stylesheet and Tailwind's `@theme` meet: whether `styles.css`'s `@theme inline` block is generated as well.

## Tracking

- [ ] Docs: this RFC, portalr ADR-0056 and ADR-0057.
- [ ] Foundation: token layers at today's values, component tokens, structural reduced motion, guard rails; zero baseline diffs.
- [ ] Loader: pair manifest, validation, `brand.css`, serving, `index.html` rewrite, `config.json`, `Site(brand=...)`, `nightshade`.
- [ ] CLI and tooling: `portalr brand`, matrix and motion playground, presets, stackr template, docs, `calm`.
