# RFC-0007: portalr brand kits

**Status:** Draft
**Author:** Alex Nodeland
**Created:** 2026-10-20
**Discussion:** the pull request that adds this file

## Summary

A deployment of portalr can be restyled by plugging in a brand kit: a folder holding `brand.json` (identity, copy, assets, font licences) and two token files in the W3C Design Tokens (DTCG) format, `tokens.light.json` and `tokens.dark.json`. portalr validates the kit in Python, compiles it to one stylesheet, `brand.css`, serves it with a content hash, and rewrites the UIs' `index.html` at serve time so the kit's title, icon and stylesheet are in place before the first paint. The kit overrides tokens and nothing else: three layers of them (primitives, semantic roles, and a full inventory of component tokens), including a motion system with guard rails. The default look becomes a kit of its own, `brand/default`, which regenerates today's `tokens.css` exactly. A kit is chosen per deployment; per tenant comes later, and the layout leaves room for it.

## Motivation

A team that deploys lattice wants the portal to look like theirs: their name in the tab, their mark in the header, their colours, type, corners, shadows and motion. Today the look is portalr's own (lattice ADR-0014, portalr ADR-0019, 0029, 0036, 0037, 0039), held in one hand-written `tokens.css` of semantic roles. Restyling means forking it, and the components still carry spacing, radii, shadows and durations of their own in their class strings, so a fork reaches only the colours.

The UI audit of 2026-10-20 found the same faults from the other side: 13 link styles and 12 button styles, ad hoc heading sizes, raw `a`, `button`, `details` and `ins` elements with the browser's own focus ring, and no `::selection` or scrollbar styling. A kit that can restyle every component needs every component to read its look from tokens; a polish pass that standardises the components needs the same. This RFC does both in one order of work.

Why now: v0.2 is the release a team first deploys, and the polish PRs are about to touch every class string. Laying the token layers down first means each polish PR lands on tokens, not on literals.

## Design

### Scope and the owner's decisions

These were decided by the owner before this RFC and are recorded here, not reopened:

- **Format:** `brand.json` plus DTCG tokens, `tokens.light.json` and `tokens.dark.json`, with aliases and typed validation.
- **Override layer:** tokens only in v0.2. No `parts.css` or other free-form CSS; perhaps in v0.3.
- **Depth:** the full component-token inventory and a motion system.
- **Scope:** per deployment. Per tenant later; the layout stays additive so it can come without a break.

### The kit's files

```
brand/<name>/
  brand.json            identity, copy, assets, fonts and their licences, presets
  tokens.light.json     DTCG tokens for the light scheme
  tokens.dark.json      DTCG tokens for the dark scheme (only what differs, or everything)
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
  "$schema": "https://lattice.dev/schemas/portalr-brand-1.json  (placeholder)",
  "version": 1,
  "name": "nightshade",
  "identity": { "product": "Nightshade", "app": "Nightshade", "admin": "Nightshade admin" },
  "copy": { "tagline": "Ask, and it is drafted.", "signIn": "Sign in to Nightshade" },
  "assets": {
    "mark": { "light": "assets/mark-light.svg", "dark": "assets/mark-dark.svg" },
    "favicon": "assets/favicon.svg",
    "themeColor": { "light": "{color.paper}", "dark": "{color.paper}" }
  },
  "fonts": [
    {
      "family": "Inter",
      "role": "sans",
      "files": [{ "path": "fonts/inter-wght.woff2", "weight": "100 900", "style": "normal" }],
      "licence": { "spdx": "OFL-1.1", "file": "fonts/LICENSE-inter.txt" }
    }
  ],
  "presets": { "shape": "soft", "motion": "subtle", "elevation": "shadow" }
}
```

Copy keys are a closed set the UIs read; an unknown key is an error, not ignored. Strings are text, never markup.

### Three token layers

Each layer is a set of CSS custom properties on `:root`. A layer reads only the layers beneath it, so a kit can change a primitive and see every role and component follow, or pin one component token alone.

1. **Primitives:** colour ramps and the inks; `--space-*`; `--radius-0` to `--radius-4`; `--font-size-*`, `--leading-*`, `--weight-*`; `--shadow-1` to `--shadow-4`; `--border-width-*`; `--duration-*`; `--ease-*`.
2. **Semantic roles:** today's names, unchanged: `--paper`, `--surface`, `--fg`, `--muted`, `--line`, `--edge`, `--accent`, `--on-accent`, `--focus`, `--danger`, `--status-*`, `--chart-*`, `--ansi-*`, `--code-token-*`, `--page-width`, `--row-height`, `--scrim`, `--shadow-color`.
3. **Component tokens,** each defaulting to a role or a primitive: `--button-radius`, `--button-pad-x`, `--button-pad-y`, `--button-weight`, `--button-shadow`, `--button-lift`, `--button-press-scale`; input, select, checkbox and switch; card; dialog (scrim blur, width, enter and exit); menu, popover and tooltip; tabs; badge; table; nav, sidebar and header; toast; chat bubbles, tool rows, question cards and the inline artifact's chrome; code block; plus focus ring, scrollbar, selection and icon stroke.

Every token today's `tokens.css` and `styles.css` declare keeps its name and its computed value. The component inventory is finished in the foundation PR, component by component.

### DTCG mapping

A token's path in the JSON becomes its custom property by joining the path with `-` under a fixed prefix per group. The mapping is a table in the loader, not a convention a kit can bend:

| DTCG path | `$type` | CSS custom property | Example value |
|---|---|---|---|
| `color.paper` | `color` | `--paper` | `#f7f4fb` |
| `color.status.failed` | `color` | `--status-failed` | `#8a0f2c` |
| `color.chart.1` | `color` | `--chart-1` | `{color.ramp.violet.700}` |
| `color.ramp.violet.700` | `color` | `--color-violet-700` | `#6b2fa0` |
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
| `component.button.radius` | by its role | `--button-radius` | `{radius.2}` |
| `component.dialog.enter` | `transition` | `--dialog-enter-*` | a closed pattern name, see motion |

`{alias}` references resolve in the loader; a cycle, an unknown path, or an alias of the wrong `$type` is an error. A token present in only one scheme's file is the same in both. The loader emits each colour that differs as one `light-dark()` pair, as `tokens.css` does today, and anything else once.

### Validation

All of it in Python, in the loader, before anything is served; `portalr brand validate` runs the same code.

- **A typed grammar, so no CSS injection.** Each `$type` has a parser that produces a value from a closed grammar (hex or `oklch()` colours, numbers with an allowed unit, a cubic-bezier of four numbers, a font family list of quoted names). Nothing from the kit reaches `brand.css` as text it wrote; the loader prints values it built. Unknown token paths are errors.
- **Contrast,** in both schemes: every text-on-surface pair the UIs use, the focus ring against what it rings, controls' edges at 3:1, status and chart marks at 3:1, ANSI and code tokens at 4.5:1. The pairs are today's token tests, moved to Python and run on any kit.
- **Colour-vision distances:** status and chart colours 20 or more apart, to CIEDE2000, for a reader who sees every colour and under simulated protanopia, deuteranopia and tritanopia (portalr ADR-0039).
- **SVG sanitisation:** an allow-list of elements and attributes; no script, `foreignObject`, event handler, external reference or `data:` URL. A size cap per file.
- **Fonts:** WOFF2 only, a size cap per file and per kit, and a licence for every family, with an SPDX id from an allowed list (OFL-1.1, Apache-2.0, MIT, or a declared commercial licence with its file).
- **Motion guard rails,** below.

### Motion

A closed set of entry and exit patterns (fade, rise, scale, slide from an edge, none), a duration scale and an easing scale, and three presets (`none`, `subtle`, `lively`). Guard rails the validator holds: no duration over 600ms, an instant step at 80ms or less, nothing that flashes more than three times a second, no shift over 24px, a scale that starts between 0.9 and 1, and an overshoot limit on easing curves.

`prefers-reduced-motion: reduce` is structural: the base stylesheet, after `brand.css`, sets every duration and shift token to its still value with `!important` custom properties, which a kit's tokens cannot undo. A kit that wants no motion at all sets the `none` preset.

### What a kit can't brand

Security chrome stays portalr's: the mini app's label and frame (portalr ADR-0051), host dialogs, the colour-blind patterns (ADR-0036), forced-colours styles, and the skip link. Their tokens are not in the kit's grammar. App frame sizing and the mini-app bridge are untouched.

### Presets

`brand.json` names a preset per axis, which sets a group of primitives that tokens can still override: shape (`sharp`, `soft`, `round`), motion (`none`, `subtle`, `lively`), elevation (`shadow`, `border`, `flat`).

### Loading and serving

- `Site(brand=...)`, a path to the kit's folder (or None for the default), validated when the application starts: a bad kit fails the start, with every fault listed.
- `config.json` gains a `brand` block: the identity, the copy, and the hashed URLs of the stylesheet and assets.
- The kit is served at `/portalr/brand/<hash>/...`, with an immutable cache header; the hash is of the compiled output.
- The UIs' `index.html` is rewritten at serve time: `<title>`, the icon links, `theme-color` meta, and a `<link rel="stylesheet">` to `brand.css` before the first paint. `scheme.js` stays as it is.
- The stackr template takes `PORTAL_BRAND_DIR`.
- A `portalr brand` CLI: `init` (a new kit from the default, with a preset), `validate`, and `preview` (the component matrix and motion playground against the kit).

### The default kit

`brand/default` holds today's look. The build generates `tokens.css` from it, and a snapshot test holds the generated file. The refactor that introduces the layers changes no pixel: the existing screenshot baselines must not move.

### Fixtures

Two example kits: `nightshade`, an ordinary one, and `calm`, an extreme one (`round`, `none`, `flat`, a different face) that proves the layers reach every component. The component matrix and the motion playground are screenshot fixtures in the vitest browser suites, run against the default and both examples.

### Guard rails for the components

From the audit, enforced in CI so the components stay on tokens: Biome's `noRestrictedElements` for raw `a`, `button`, `table`, `select`, `details`, `summary` and `ins` outside the kit's own components; a test that refuses hex, `rgb()`, arbitrary px or rem values and `color-mix()` outside `tokens.css` and `styles.css`; and a style-census test in the screenshot suites that counts distinct link, button and heading styles.

### Staging

Each step is one PR, reviewable alone.

0. **Docs:** this RFC, portalr ADR-0056 (token layers, loading, validation) and ADR-0057 (motion, and tokens as the only override layer).
1. **Foundation:** primitives, radius, shadow and motion tokens at today's computed values; the component tokens, one component per commit, with computed-style snapshot tests that prove no change; the structural reduced-motion block; the guard rails. Zero screenshot baseline diffs. Lands after the in-flight UI PRs (#428, #431, #434, #435), as it touches every class string.
2. **Loader:** `brand.json` and DTCG parsing, validation, `brand.css`, `Site(brand=...)`, serving, the `index.html` rewrite, `config.json`'s block, and `nightshade`. Can run in parallel with the polish PRs.
3. **CLI and kit tooling:** `portalr brand init/validate/preview`, the component matrix and motion playground, presets, the stackr template's `brand/` and `PORTAL_BRAND_DIR`, the docs, and `calm`.

The polish PRs (links and breadcrumbs, list rows, icon buttons and tooltips, badge, code and kbd, disclosure, the shell, states) follow the foundation and land on its tokens.

## Drawbacks

- Hundreds of custom properties, and a refactor that touches every component. The zero-diff gate and the per-component commits are what make it reviewable.
- A token-only kit can't change a layout or a component's shape beyond what its tokens reach. That is the point in v0.2, and the reason for the full inventory.
- Validation in Python means the TypeScript side trusts the compiled `brand.css`; the type grammar is the one place it must be right.
- A content hash in a URL and an `index.html` rewritten at serve time are two more things to cache correctly.

## Alternatives

- **A `parts.css` override** of free-form CSS: reaches anything, but can break the security chrome and every screenshot, and can't be validated. Deferred to v0.3 at the earliest (owner's decision).
- **A theme in TypeScript,** compiled into the bundle: a kit would need a build per deployment. The same UIs serving every deployment is a rule of `Site` today.
- **Style Dictionary or another token compiler** in the build: a Node dependency at runtime for a Python service, and it validates no contrast. The mapping table is small enough to own.
- **Tokens as YAML or a flat CSS file:** no aliases or types (YAML), or nothing to validate (CSS). DTCG is a standard other tools export.
- **Per tenant now:** needs the kit in the database and a stylesheet per request. The layout leaves room for it (owner's decision).

## Decided in discussion

The owner settled these on the pull request:

- **The default marks are fully replaceable.** portalr's and grantr's marks and the lattice inks (lattice ADR-0001, ADR-0014) ship with the code under MIT, with a trademark note: the marks stay lattice's trademark and are not licensed for reuse as someone else's product, but a kit may remove or replace them. No separate licence, and no attribution is required. `portalr brand init` says so.
- **`tokens.dark.json` holds only what differs** from `tokens.light.json`; a token absent from it is the same in both schemes.
- **A kit's fonts are not shared with mini apps** until v0.3.
- **The schema URL is a placeholder.** `https://lattice.dev/schemas/portalr-brand-1.json` above stands in for a URL to be chosen; no domain is claimed by it.
- **The style census reports in the foundation PR** and fails the build once the polish PRs have landed. The Biome raw-element rule and the literal-value test fail the build from the start.

## Unresolved questions

- None open at this stage; new ones go here as the PRs raise them.

## Tracking

- [ ] Docs: this RFC, portalr ADR-0056 and ADR-0057.
- [ ] Foundation: token layers at today's values, component tokens, structural reduced motion, guard rails; zero baseline diffs.
- [ ] Loader: validation, `brand.css`, serving, `index.html` rewrite, `config.json`, `Site(brand=...)`, `nightshade`.
- [ ] CLI and tooling: `portalr brand`, matrix and motion playground, presets, stackr template, docs, `calm`.
