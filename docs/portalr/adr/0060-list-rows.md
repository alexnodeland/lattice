# ADR-0060: List rows: a title, a quieter line beneath it, and an end

**Status:** Accepted
**Date:** 2026-10-21
**Deciders:** Alex Nodeland

## Context

The UI audit of 2026-10-20 found the app's lists (threads, artifacts, rules, a tenant's workspaces, people with access) drawn as underlined links in the working colour on hairlines. Each row put its link, its id, its kind and its status on one wrapping line, so a long title pushed the rest under it at any width, and every row shouted as loudly as the next. `Row` took any children, so each list chose its own layout.

## Decision

- **A row has three parts:** its `title`, on the first line; its `meta`, what is said about it, quieter (`--muted`), on the line beneath; and its `end`, what it is doing or what can be done to it (a status, a badge, an action, links of its own), aligned to the row's end. Each part truncates rather than wraps the next under it.
- **A row's title, when it is a link, is in the text's colour and not underlined,** and takes the working colour and an underline when hovered or reached from the keyboard. It still stretches over the whole row, so the row is its target, as before. What is at the row's end sits above the stretched link and stays a target of its own.
- **Tokens:** `--list-row-pad-x`, `--list-row-pad-y`, `--list-row-gap` and `--list-row-line-gap`. The hairlines and the hover wash are unchanged.
- **`Row`'s API breaks inside portalr's UIs:** `title`, `meta` and `end` replace free children. Every list moves onto it: tenants (app and admin), a tenant's workspaces, threads, artifacts, rules and schedules, and people with access.
- **Left for later:** the runs list and the tracker items are not `Row`s yet; they move when the link variants (ADR-0059) are on main, as their links need the `subtle` and `external` variants.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Layout | **Title, meta beneath, end (chosen)** | Scans down the titles; a long title doesn't move the rest | Two lines a row |
| | One wrapping line, as before | Dense | Each row a different shape |
| Title's look | **Text colour, underlined when hovered (chosen)** | A list reads as a list, not a page of links | Its link-ness is in its hover and its row |
| | Working colour, underlined | Plainly a link | Every row shouts |

## Consequences

- Easier: a new list is a `Row` with three slots, and a kit restyles every list by four tokens.
- Harder: a row that needs more than three parts has to choose what goes in its meta.
- To revisit: the runs list and the tracker items, once ADR-0059 is on main.
