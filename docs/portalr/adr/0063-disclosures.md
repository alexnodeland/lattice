# ADR-0063: Disclosures

**Status:** Proposed
**Date:** 2026-10-21
**Deciders:** Alex Nodeland

## Context

The UI audit of 2026-10-20 ([lattice RFC-0007](../../rfcs/0007-portalr-brand-kits.md)) found eleven parts that open and close drawn as raw `details` and `summary`, each with its own look: the browser's marker or a chevron of the page's own, its focus ring or the kit's, a target as small as the line of text. A chart's "Show the figures", a tool call, a revision, a JSON tree's folds, a native file's comparison and a failed run's "Details" each opened differently. This is polish PR 5 of the audit.

## Decision

- **`Disclosure`** is the kit's part that opens and closes, on Base UI's Collapsible. Its summary is a button: it says whether it is open (`aria-expanded`) and, open, what it opens (`aria-controls`), and Enter and Space work it. It has the kit's focus ring, a target at least `--disclosure-target` (24px) tall, and a chevron that turns in `--disclosure-duration`, not at all under reduced motion. `name` names the trigger where its summary alone wouldn't tell it from its neighbours'. Its panel is hidden until found while closed (`hidden="until-found"`), so a find in the page reaches what it holds and opens it: a chart's, a tracker's and a dashboard's figures, a JSON tree's folds, a failed run's details, a tool call's arguments, a run's history. A revision, a native file's words and a proposal's comparison render what they open only once opened, to read it only when asked, as they did inside `details`: there a find has nothing to reach until then.
- **Three looks:** `quiet` (a muted line, "Show the figures", "Details", a JSON tree's folds), `link` (the working colour, underlined on hover: a native file's "Changes to its words", a proposal's comparison) and `block` (the width of what it opens, laid out by its summary: a revision, a tool call). A caller's classes are for its box and its trigger's layout, never the trigger's colour.
- **Tokens:** `--disclosure-target`, `--disclosure-gap`, `--disclosure-radius`, `--disclosure-panel-gap` and `--disclosure-duration`, in the kit's DTCG component layer and the generated `tokens.css`.
- **Converted:** 11 disclosures in 10 files: `chart.tsx` (two), `dashboard-figures.tsx`, `tracker.tsx`, `json-view.tsx`, `revisions.tsx`, `run-failed.tsx`, `tool-call.tsx`, app's `native-file.tsx` and `native-proposal.tsx`, and admin's runs page (a run's history). A dashboard's figures are held open by the page once its chart can't be drawn, even when that is known only after the first render. The trace view's fold toggle is not a disclosure: the row is the tree's item, and its keys fold it; the toggle is a pointer's shortcut, hidden from assistive technology, and is now the kit's `Button`.
- **Guard rails:** the eleven files converted, the trace view's with them, come off Biome's raw-element list. It keeps five: the two UIs' `main.tsx`, `artifacts.tsx`, `file-preview.tsx` and the dashboards' add-on.
- **What looks different:** the gap after the chevron is `--disclosure-gap` (6px), where a tool call's and a revision's were 8px; a block's chevron is 16px with a 2px drop, so a tool call's, which was 14px and centred, sits about 2px lower; a JSON tree's folds are 24px targets, so a tree's rows are taller; the focus ring is the kit's solid 2px, where a `quiet` or `link` summary had the browser's; the trace view's toggle, now a ghost `Button`, has a hover wash, a press shift and corners, and is still hidden from assistive technology and out of the tab order.

## Consequences

- Easier: a kit restyles every part that opens through one component and its tokens.
- Harder: a closed panel keeps Base UI's starting style while hidden, so the computed-style gate now waits only for elements that are shown to finish entering.
- Harder: `aria-controls` is set only while open, as Base UI sets it; a closed trigger names no panel.
