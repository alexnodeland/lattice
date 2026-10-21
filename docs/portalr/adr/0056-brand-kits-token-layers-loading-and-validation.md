# ADR-0056: Brand kits: three token layers, a kit loaded per deployment, and validation in Python

**Status:** Proposed
**Date:** 2026-10-20
**Deciders:** Alex Nodeland
**Relocates:** the tokens of [ADR-0019](0019-the-kits-look.md), [ADR-0036](0036-the-chart-theme-and-colour-blind-mode.md) and [ADR-0039](0039-elevation-status-colour-states-and-density.md), which keep their names and values and move into the default kit

## Context

[lattice RFC-0007](../../rfcs/0007-portalr-brand-kits.md) proposes brand kits: a deployment restyles portalr by plugging in a folder. The owner chose the format (`brand.json` and DTCG tokens per scheme), the depth (every component on tokens) and the scope (per deployment). Today `tokens.css` holds semantic roles only; components carry radii, spacing, shadows and durations as literals in their class strings, so a kit could reach only colour. The UIs are one build that serves every deployment, with what differs in `config.json` (`Site`).

## Decision

- **Three layers of custom properties.** Primitives (colour ramps and inks, space, radius, type size, leading and weight, shadows, border widths, durations, easings); semantic roles (today's names, unchanged); component tokens, each defaulting to a role or a primitive (button, input and its kin, card, dialog, menu, popover, tooltip, tabs, badge, table, nav, sidebar, header, toast, the chat's bubbles, tool rows, question cards and inline artifact chrome, code block, focus ring, scrollbar, selection, icon stroke). A layer reads only the ones beneath it. A component's styles read its component tokens, which default to roles and primitives.
- **A kit is a delta over the default kit,** `brand/default`, resolved as default, then presets, then the kit's light tokens, then its dark tokens laid over light; aliases resolve per scheme after layering. A token a kit doesn't name keeps its default. The inventory is version 1 when the foundation PR merges; additions bump it with a default, renames are a major version.
- **The default look is the default kit.** A generated, checked-in stylesheet replaces the hand-written `tokens.css`, with a regenerate-and-diff test; it will not match today's file byte for byte. Separately, every computed value stays what it is: computed-style snapshots per component (states, both schemes, forced colours, reduced motion, transition and animation properties) and the screenshot baselines hold it.
- **A kit is `brand.json` and DTCG token files,** `tokens.light.json` and `tokens.dark.json`, with assets and fonts beside them. Paths map to custom properties by a lookup table in the loader, one row per token; a path with no row is an error. The loader targets DTCG draft 2025.10 with a documented profile (RFC-0007). Aliases are at most 8 deep; a cycle, an unknown path or a type mismatch is an error. A colour that differs between schemes is one `light-dark()` pair; another token that differs is emitted per colour with `light-dark()` or in a dark block mirroring `data-theme` and `prefers-color-scheme`. Derived colours (`--wash`, `--accent-hover`, `--danger-hover`, `--chart-grid`) are computed by the loader, not written by a kit.
- **Validation is in Python,** once, when the application starts and in `portalr brand validate`: a typed grammar per `$type` from which the loader builds every value it prints, so no text a kit wrote reaches CSS but family names, which it checks and quotes; a checked-in pair manifest of contrast pairs, shared with the UI's token tests, in both schemes, with alpha composited over a named backdrop; CIEDE2000 distances (Machado, severity 1.0) for the status and chart colours; accessibility floors (focus ring, 24px targets, body size, a boundary under flat elevation), which hold for the app, with admin's compact density a deliberate exception that a kit can't shrink further; an SVG allow-list; WOFF2 fonts by magic number with size caps, and a licence each, as the author's attestation. A bad kit fails the start with every fault listed.
- **Loaded per deployment.** `Site(brand=...)` names the kit's folder; `config.json` gains a `brand` block (identity, copy, hashed URLs). The compiled `brand.css` and the assets are served at `/portalr/brand/<hash>/` (the hash covering the stylesheet, every asset and font, and the brand block), only for manifest paths, with `nosniff`, an explicit type and an immutable cache header, and SVGs under a sandboxing CSP. The header mark is an `<img>`. The UIs' `index.html` is rewritten at serve time with the title, icons, `theme-color` and the stylesheet link, with every string escaped, served `no-cache` with an `ETag`, so the kit is in place before the first paint; `scheme.js` is unchanged. The stackr template takes `PORTAL_BRAND_DIR`.
- **Security chrome is outside the grammar:** the mini app's label and frame, host dialogs, the skip link, the colour-blind patterns and forced-colours styles read a pinned set of chrome tokens derived from validated roles, with their own pairs in the manifest (including against the kit's surfaces), and the default's values where a pair fails. `brand.css` never sets `color-scheme` or `forced-color-adjust`, has no `@import` and no `url()` but its fonts, and precedes the base stylesheet. App frame sizing and the mini-app bridge are untouched.
- **Guard rails keep components on tokens:** Biome's `noRestrictedElements` for raw `a`, `button`, `table`, `select`, `details`, `summary` and `ins` outside the kit's own components; a test refusing hex, `rgb()`, arbitrary px or rem and `color-mix()` outside `tokens.css` and `styles.css`; a style census in the screenshot suites, which reports at first and fails the build once the polish PRs have landed; the other two fail from the start.

## As built

The foundation PR (#452) departs from this decision as [lattice RFC-0007](../../rfcs/0007-portalr-brand-kits.md#foundation-pr-as-built) lists: derived colours stay `color-mix()` in `base.css` until the loader PR computes them; the literal-value test exempts `tokens.css`, `base.css` and `styles.css`; the corner and shadow scales are as wide as today's values; some component tokens are literals; colour ramps come later.

The loader PR (#519) departs from the decision above as RFC-0007's "Loader PR as built" lists: `brand.css` comes after the UI's stylesheet, and what colour-blind mode swaps is declared outside it; the pair manifest names a backdrop for clear colours; faces are checked by header, with the browser's sanitiser as the real defence; nothing in the UIs reads the `config.json` block yet; and the chrome tokens, presets and `oklch()` are not built.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Format | **`brand.json` and DTCG per scheme (chosen, by the owner)** | A standard design tools export; typed; aliases | A mapping table to own |
| | One CSS file | Nothing to compile | Nothing to validate; injection by construction |
| | YAML | Easy to write | No types or aliases |
| Depth | **Every component on tokens (chosen, by the owner)** | A kit reaches shape, density and motion, not only colour | A refactor of every class string |
| | Roles only | Small | A kit restyles colours and nothing else |
| Validation | **Python, at start (chosen)** | One place; the service refuses a bad kit before it serves it | The browser trusts the compiled stylesheet |
| | TypeScript, in the build | Beside the components | A build per deployment |
| Delivery | **Served stylesheet and `index.html` rewritten (chosen)** | One build for every deployment; no flash | A rewrite to cache correctly |
| | Inlined at build | Simple | A build per kit |
| Scope | **Per deployment (chosen, by the owner)** | One stylesheet per process | A tenant can't have its own; the layout leaves room |

## Consequences

- Easier: restyling a deployment is a folder and a setting; every component's look is a named token; a polish PR lands on tokens, not literals.
- Harder: hundreds of custom properties to name and keep; the type grammar must be right, since it is what stands between a kit and the page.
- To revisit: per-tenant kits; fonts shared with mini apps (v0.3). The default marks ship under MIT with a trademark note and are fully replaceable in a kit (RFC-0007).

## Action items

1. [ ] Foundation PR: the layers at today's values, component tokens one commit each, computed-style snapshots, guard rails; zero baseline diffs.
2. [ ] Loader PR: parsing, validation, `brand.css`, `Site(brand=...)`, serving, `index.html` rewrite, `config.json`, the `nightshade` kit.
3. [ ] Tooling PR: `portalr brand init/validate/preview`, presets, the stackr template, docs, the `calm` kit.
