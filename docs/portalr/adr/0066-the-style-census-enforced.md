# ADR-0066: The style census, enforced

**Status:** Proposed
**Date:** 2026-10-22
**Deciders:** Alex Nodeland

## Context

The style census ([lattice RFC-0007](../../rfcs/0007-portalr-brand-kits.md)) counts the distinct looks of the galleries' links, buttons and headings at rest. Until now it only reported them, and was meant to fail once the polish pass was done. With slices 1 to 8 merged, this is slice 9: the census was run as an enforcing check, and every look it counted was traced to its source.

## Decision

- **The census enforces an exact count** for each kind: 12 links, 21 buttons and 3 headings, the same in light and dark. The test's `LOOKS` table names each look, kind by kind, and its lengths are the counts. The test fails if the count is under its length ("fewer looks than the ceiling: lower `LOOKS.<kind>` to N") or over it ("more looks than the ceiling: raise it only if the kit gained a variant, and name it in `LOOKS.<kind>`"). An exact count catches a look that goes, so the ceiling comes down with it and can't later make room for a new look unnoticed. A swap in one change, one look going and another coming, still keeps the count and isn't caught; the computed-style snapshots would show it. The names account for the count; they aren't matched one by one to the computed signatures, because a look's signature names no component. CI already runs the census with the screenshot suites, so it enforces from this change.
- **What it found that wasn't a kit variant:**
  - The disclosure's link look used a literal underline offset. It now uses `--link-underline-offset`, which is the same 2px.
  - The JSON view and the line diff used a literal `32rem` as their height before they scroll. It is now a kit token, `--code-block-max-height`, at the same 32rem.
  - Both literals leave the literal-value list.
- **Kept, with the reason:**
  - The Sheet gallery's "Usage" is a raw `<a>` in a test fixture, not in a product file. Changing it would move a computed snapshot and a screenshot for no product change.
  - Biome's raw-element exceptions are now three, each a use the kit has no component for: a spreadsheet's grid (`file-preview.tsx`, `<table>`), an added word in a comparison (`artifacts.tsx`, `<ins>`), and a sortable column's header (`on-demand/dashboards.tsx`, `<button>` inside `<th>`).
  - The literal-value list keeps 15 entries. They are layout lengths particular to one screen, such as a panel's width beside a list, a grid's minimum column, or an embedded frame's height. Making each a token would put screen layout into the brand kit.

## Consequences

- A new link, button or heading look fails CI until it is folded into a kit variant, or the kit gains one.
- **What the census doesn't see.**
  - It selects `a[href]`, `button`, `[role=button]` and `h1` to `h6`. It doesn't select `[role=link]`, tabs or menu items that aren't buttons, `summary`, or `input[type=button]`. None of these are in the galleries today, but one added would go uncounted.
  - It counts looks at rest only. A hover, focus or pressed state that differs between two same-looking controls isn't counted; the computed-style snapshots cover those states scene by scene.
- Badges are counted too, since 2026-10-22: `Badge` and `StatusBadge` carry `data-badge`, which the census selects, and their looks are 6, the same in light and dark: the status tones' five (the accent's fill; the failed edge; quiet, on the line; the warning edge; the text's colour, on the line) and `Badge`'s accent. `Badge`'s neutral look is in no gallery, so it isn't counted until one shows it.
