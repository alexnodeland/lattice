# ADR-0063: Disclosures

**Status:** Proposed
**Date:** 2026-10-21
**Deciders:** Alex Nodeland

## Context

The UI audit of 2026-10-20 ([lattice RFC-0007](../../rfcs/0007-portalr-brand-kits.md)) found eleven parts that open and close drawn as raw `details` and `summary`, each with its own look: the browser's marker or a chevron of the page's own, its focus ring or the kit's, a target as small as the line of text. A chart's "Show the figures", a tool call, a revision, a JSON tree's folds, a native file's comparison and a failed run's "Details" each opened differently. This is polish PR 5 of the audit.

## Decision

- **`Disclosure`** is the kit's part that opens and closes, on Base UI's Collapsible. Its summary is a button: it says whether it is open (`aria-expanded`) and, open, what it opens (`aria-controls`), and Enter and Space work it. It has the kit's focus ring, a target at least `--disclosure-target` (24px) tall, and a chevron that turns in `--disclosure-duration`, not at all under reduced motion. What it opens stays in the page while closed, hidden until found, as a `details` element's does, so a find in the page reaches it.
- **Three looks:** `quiet` (a muted line, "Show the figures", "Details", a JSON tree's folds), `link` (the working colour, underlined on hover: a native file's "Changes to its words", a proposal's comparison) and `block` (the width of what it opens, laid out by its summary: a revision, a tool call). A caller's classes are for its box and its trigger's layout, never the trigger's colour.
- **Tokens:** `--disclosure-target`, `--disclosure-gap`, `--disclosure-radius`, `--disclosure-panel-gap` and `--disclosure-duration`, in the kit's DTCG component layer and the generated `tokens.css`.
- **Converted:** charts (two), a dashboard's figures, a tracker's figures, a JSON tree, revisions, a failed run's details, a tool call, and the native file's and a proposal's comparisons. The trace view's fold toggle is not a disclosure: the row is the tree's item, and its keys fold it; the toggle is a pointer's shortcut, hidden from assistive technology, and is now the kit's `Button`.
- **Guard rails:** the ten files converted come off Biome's raw-element list. It keeps six: the two UIs' `main.tsx`, `artifacts.tsx`, `file-preview.tsx`, the dashboards' add-on, and admin's runs page, whose disclosures wait for #524, which changes that file.

## Consequences

- Easier: a kit restyles every part that opens through one component and its tokens.
- Harder: a closed panel keeps Base UI's starting style while hidden, so the computed-style gate now waits only for elements that are shown to finish entering.
