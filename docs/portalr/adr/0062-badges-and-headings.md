# ADR-0062: Badges and headings

**Status:** Proposed
**Date:** 2026-10-21
**Deciders:** Alex Nodeland

## Context

The UI audit of 2026-10-20 ([lattice RFC-0007](../../rfcs/0007-portalr-brand-kits.md)) found headings set by hand, page by page: 16 below the page's own, as `font-semibold` with or without a size, or as a type entry spelled out each time. It also found pills drawn by hand beside `StatusBadge`: a revision's "Latest", an option's "Recommended", each with its own corners and padding, one with no edge under forced colours. This is polish PR 4 of the audit, after links (ADR-0059), list rows (ADR-0060) and icon buttons (ADR-0061).

## Decision

- **`Heading`** takes a `level` (2 to 4, as the outline needs) and a `look` from the kit's type scale: `section`, `subsection` (new in `TYPE`: the base size, semibold, between a section's and a label), `label` or `labelQuiet`. The level says where a heading sits, the look how much it weighs, so a card's title can be an `h3` and still read as a label. `className` is for layout alone, such as breaking a long word. `SectionTitle` is `Heading` at level 2, as a section. The page's one `h1` stays `PageHeader`'s.
- **Every heading in ui, app and admin below the page's** is a `Heading` or a `SectionTitle`: the 16 written by hand in the trace and log views, the cards and panels, the dashboards' panels, a form's sections, a mini app's chrome, a revision's parts, and the usage page's.
- **`Badge`** is a word in a pill that says what something is, not how it is going, which stays `StatusBadge`'s. It is `neutral` (quiet, on the surface) or `accent` (the working colour, for the one thing the reader is pointed to). It takes the badge's corners and padding (`--badge-radius`, `--badge-pad-y`, `--badge-pad-end` on both sides), and always has an edge, so a forced-colours reader sees it as a pill. Its pairs are already in the manifest: `muted` on `surface`, and `on-accent` on `accent`. "Latest" and "Recommended" are badges now.
- **Not badges, and why:** the nav's count is a counter beside a link, on its own token (`--nav-count-radius`). A question's answer chip is a truncating label of what was answered, on its own token (`--question-chip-radius`). Neither says what a thing is.

## Consequences

- Easier: a kit restyles every heading below the page's through the type scale, and every label pill through the badge's tokens.
- Harder: the style census's galleries hold none of the headings converted here, so its heading count, 3, doesn't move. The computed-style snapshots show the change instead: a recommended option's badge, now with its edge and the badge's padding.
