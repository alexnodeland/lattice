# ADR-0066: The style census, enforced

**Status:** Proposed
**Date:** 2026-10-22
**Deciders:** Alex Nodeland

## Context

The style census ([lattice RFC-0007](../../rfcs/0007-portalr-brand-kits.md)) counts the distinct looks of the galleries' links, buttons and headings at rest. Until now it only reported them, and was meant to fail once the polish pass was done. With slices 1 to 8 merged, this is slice 9: the census was run as an enforcing check, and every look it counted was traced to its source.

## Decision

- **The census enforces a ceiling** for each kind (`MOST`): 12 for links, 21 for buttons, 3 for headings, the same in light and dark. Each look is accounted for as a kit variant in the test's comment. It is a ratchet: lowered when looks are folded together, raised only with a new kit variant and a line in that comment. CI already runs it with the screenshot suites, so it enforces from this change.
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
- Badges aren't counted: `Badge` and `StatusBadge` carry no attribute the census can select. Counting them is a follow-up.
