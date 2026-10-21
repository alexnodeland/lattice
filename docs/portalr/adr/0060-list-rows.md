# ADR-0060: List rows: a name, a quieter line beneath it, and an end

**Status:** Proposed
**Date:** 2026-10-21
**Deciders:** Alex Nodeland

## Context

The UI audit of 2026-10-20 found the app's lists (threads, artifacts, rules, a tenant's workspaces, people with access) drawn as underlined links in the working colour on hairlines. Each row put its link, its id, its kind and its status on one wrapping line, so a long title pushed the rest under it at any width, and every row shouted as loudly as the next. `Row` took any children, so each list chose its own layout.

## Decision

- **A row has three parts:** its `name`, first, wrapping as long as it needs, which may be several blocks, such as a run's rule, its last failure and its tracker items; its `meta`, what is said about it, quieter (`--muted`), on the line beneath, wrapping rather than cut, so nothing in it is hidden; and its `end`, what it is doing or what can be done to it (a status, a badge, an action, links of its own). From the small breakpoint the end is aligned to the row's end and takes at most half the row; below it, the end goes under the meta, so a long end never squeezes the name. The prop is `name`, not `title`, which is an HTML attribute.
- **A row's name, when it is a link (`RowLink`), looks like a subtle link (ADR-0059):** the text's colour with a quiet `--edge` underline, so it reads as a link on a touch screen too, taking the working colour when hovered or reached from the keyboard. It still stretches over the whole row, so the row is its target, as before. What is at the row's end sits above the stretched link and stays a target of its own.
- **Tokens:** `--list-row-pad-x`, `--list-row-pad-y`, `--list-row-gap` and `--list-row-line-gap`. The hairlines and the hover wash are unchanged.
- **`Row`'s API breaks inside portalr's UIs:** `name`, `meta` and `end` replace free children. The app's and admin's lists move onto it: tenants (app and admin), a tenant's workspaces, threads, artifacts, rules and schedules, people with access, and a phone's run cards, which become rows of a list. A tracker item's link becomes an `external` link (ADR-0059).
- **Not rows:** the runs table from the small breakpoint and admin's tables (`ItemTable`) stay tables, as their rows have columns to compare, and admin's compact density is exempt from the kit floors (RFC-0007). A revision is a disclosure, and admin's runs page has disclosures too; both move with the disclosures PR, and stay on Biome's raw-element list until then.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Layout | **Title, meta beneath, end (chosen)** | Scans down the titles; a long title doesn't move the rest | Two lines a row |
| | One wrapping line, as before | Dense | Each row a different shape |
| Name's look | **Text colour with a quiet underline, the accent when hovered or focused (chosen)** | A list reads as a list, not a page of links; still a link on touch | Quieter than a link in text |
| | Working colour, underlined | Plainly a link | Every row shouts |
| | Text colour, no underline at rest | Quietest | Nothing says it is a link on a touch screen |

## Consequences

- Easier: a new list is a `Row` with three slots, and a kit restyles every list by four tokens.
- Harder: a row that needs more than three parts has to choose what goes in its meta.
- To revisit: the revisions' and admin runs' disclosures, with the disclosures PR.
