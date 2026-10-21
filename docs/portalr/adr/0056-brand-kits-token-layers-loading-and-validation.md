# ADR-0056: Brand kits: three token layers, a kit loaded per deployment, and validation in Python

**Status:** Proposed
**Date:** 2026-10-20
**Deciders:** Alex Nodeland
**Amends:** the tokens of [ADR-0019](0019-the-kits-look.md), [ADR-0036](0036-the-chart-theme-and-colour-blind-mode.md) and [ADR-0039](0039-elevation-status-colour-states-and-density.md), which keep their names and values and move into the default kit

## Context

[lattice RFC-0007](../../rfcs/0007-portalr-brand-kits.md) proposes brand kits: a deployment restyles portalr by plugging in a folder. The owner chose the format (`brand.json` and DTCG tokens per scheme), the depth (every component on tokens) and the scope (per deployment). Today `tokens.css` holds semantic roles only; components carry radii, spacing, shadows and durations as literals in their class strings, so a kit could reach only colour. The UIs are one build that serves every deployment, with what differs in `config.json` (`Site`).

## Decision

- **Three layers of custom properties.** Primitives (colour ramps and inks, space, radius, type size, leading and weight, shadows, border widths, durations, easings); semantic roles (today's names, unchanged); component tokens, each defaulting to a role or a primitive (button, input and its kin, card, dialog, menu, popover, tooltip, tabs, badge, table, nav, sidebar, header, toast, the chat's bubbles, tool rows, question cards and inline artifact chrome, code block, focus ring, scrollbar, selection, icon stroke). A layer reads only the ones beneath it. Components read component tokens and nothing else.
- **The default look is a kit,** `brand/default`. `tokens.css` is generated from it and a snapshot test holds the file. Every computed value stays what it is: the refactor that introduces the layers moves no screenshot baseline, and a computed-style snapshot per component proves it.
- **A kit is `brand.json` and DTCG token files,** `tokens.light.json` and `tokens.dark.json`, with assets and fonts beside them. Paths map to custom properties by a fixed table in the loader (RFC-0007 lists it); aliases resolve in the loader, and a cycle, an unknown path or an alias of the wrong type is an error. A colour that differs between the schemes is emitted as one `light-dark()` pair, as today.
- **Validation is in Python,** once, when the application starts and in `portalr brand validate`: a typed grammar per `$type` from which the loader builds every value it prints, so no text a kit wrote reaches CSS; contrast pairs in both schemes, the focus ring among them; CIEDE2000 distances for status and chart colours under each simulated deficiency; an SVG allow-list; WOFF2 fonts with a size cap and a licence each. A bad kit fails the start with every fault listed.
- **Loaded per deployment.** `Site(brand=...)` names the kit's folder; `config.json` gains a `brand` block (identity, copy, hashed URLs). The compiled `brand.css` and the assets are served at `/portalr/brand/<hash>/` with an immutable cache header. The UIs' `index.html` is rewritten at serve time with the title, icons, `theme-color` and the stylesheet link, so the kit is in place before the first paint; `scheme.js` is unchanged. The stackr template takes `PORTAL_BRAND_DIR`.
- **Security chrome is outside the grammar:** the mini app's label and frame, host dialogs, the colour-blind patterns, forced-colours styles and the skip link. App frame sizing and the mini-app bridge are untouched.
- **Guard rails keep components on tokens:** Biome's `noRestrictedElements` for raw `a`, `button`, `table`, `select`, `details`, `summary` and `ins` outside the kit's own components; a test refusing hex, `rgb()`, arbitrary px or rem and `color-mix()` outside `tokens.css` and `styles.css`; a style census in the screenshot suites, which reports at first and fails the build once the polish PRs have landed; the other two fail from the start.

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
