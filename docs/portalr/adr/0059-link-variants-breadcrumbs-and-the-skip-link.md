# ADR-0059: Link variants, breadcrumbs, and the skip link

**Status:** Accepted
**Date:** 2026-10-21
**Deciders:** Alex Nodeland

## Context

The UI audit of 2026-10-20 found one link component, `TextLink`, styled thirteen ways by its callers, and a page's way back as a lone 12px underlined link, a target 24 by 16 pixels on a phone. External links were made by hand, some without `noopener`, and none said that they open a new tab. The skip link was markup inside the frame. This is the first polish PR on the token layers of [ADR-0056](0056-brand-kits-token-layers-loading-and-validation.md).

## Decision

- **`TextLink` has four variants.**
  - `inline` is running text: the working colour, underlined. It is the default and is unchanged.
  - `subtle` is an id or a name standing alone, in a table's cell, a row or a breadcrumb: the text's colour, with an underline in `--edge` (3:1 on the paper) that takes the working colour when hovered. It is never used in running text, where only its underline would tell it from the words around it (WCAG 1.4.1).
  - `nav` is one of a few places to go: the working colour, underlined only when hovered, at the small size.
  - `external` is inline and opens another site in a new tab. Its `target="_blank"` and `rel="noopener noreferrer"` are set after the caller's props, so a caller can't weaken them. A mark (`--link-mark-size`, `--link-mark-gap`) stays on the line with the last word, and "(opens in a new tab)" is said to assistive technology.
- **`Breadcrumbs` is the way back up.** It is a navigation named "Breadcrumb" listing the places above the page, outermost first, as `subtle` links at least `--breadcrumb-target` (24px) tall, separated by a `/` hidden from assistive technology. The page itself is its heading, not a crumb, since a crumb is a way somewhere and the page is already here. An empty trail shows nothing.
- **`PageHeader`'s `crumb` slot becomes `breadcrumbs`,** which takes a trail rather than any node. This is an API break inside portalr's UIs only. The crumb's words grow from the note's size (12px) to the meta's (14px), so that they are a target.
- **`SkipLink` is a component of its own.** It is security chrome, which no kit restyles (lattice RFC-0007), and it is the first stop of the keyboard, leading to `#main`.
- **Left for later polish PRs:** the tracker items' external link keeps its own markup and its own label until the list rows PR, and Markdown's links stay Streamdown's, which Biome's raw-element list allows.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Variants | **Four variants of one component (chosen)** | One import; every caller says what its link is | A variant per use |
| | One component per variant | Each has its own name | Four imports where one does |
| Breadcrumb's last item | **The page is its heading, not a crumb (chosen)** | No link to where you are | Departs from the pattern that shows the current page greyed |
| | The current page as an unlinked crumb | Common | Says the heading twice |
| External | **Mark and words, and the security attributes fixed (chosen)** | Said to every reader; never without `noopener` | A caller can't open in the same tab |

## Consequences

- Easier: a link says what it is, and a kit restyles each kind of link.
- Harder: a new caller has to choose a variant, and an inline id should become `subtle` only where it stands alone.
- To revisit: the list rows, whose links are polish PR 2.
