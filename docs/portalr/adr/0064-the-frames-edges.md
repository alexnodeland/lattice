# ADR-0064: The frame's edges

**Status:** Proposed
**Date:** 2026-10-21
**Deciders:** Alex Nodeland

## Context

The UI audit of 2026-10-20 ([lattice RFC-0007](../../rfcs/0007-portalr-brand-kits.md)) found four small things at the edges of the frame. When the skip link was focused it slid down over the mark. The rail had no test holding it in the window. Selected text and the scrollbars used the browser's colours, not the kit's. And below `lg` the pinned header covered whatever a link or the keyboard scrolled to. This is polish PR 6 of the audit.

## Decision

- **The skip link takes its own room.** It is hidden from sight until focused. Focused, it is a bar across the top of the frame (`col-span-full`) that pushes the frame down rather than lying over the mark. It is still the first stop and still leads to `#main`. It is security chrome, which no kit restyles.
- **The rail stays in the window.** From `lg` the header is a rail the height of the window, pinned at the top while the page scrolls past it. It already behaved this way; a test now holds it. Its width is a kit token, `--rail-width` (15.5rem, as before), so the literal leaves the literal-value list.
- **Selection is a deeper wash.** `::selection` is `--selection`, mixed in base.css as 22% accent over paper (the wash is 10%), so a selection still shows over a washed row. Selected text is `--fg`. The pair `fg` on `selection` (4.5) is in the manifest, and the validator mixes `--selection` as base.css does.
- **Scrollbars take the kit's colours.** The root's `scrollbar-color` is `--line` on `--paper`.
- **A scroll stops below the pinned header.** Below `lg`, the root's `scroll-padding-top` is `--header-clearance`, a new kit token (3.5rem, more than the header's height). At `lg` the header is beside the page, and the padding is 0.

## Consequences

- Easier: a focused skip link no longer hides the mark. Following a link to an anchor on a phone no longer lands the target under the header.
- A kit that sets a much taller header needs `--header-clearance` to match. A test checks the default against the header's real height.
- The computed-style gate's change is only the skip link's line in each scene with a frame. No other scene moves.
