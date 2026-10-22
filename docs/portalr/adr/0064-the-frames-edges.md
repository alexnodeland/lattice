# ADR-0064: The frame's edges

**Status:** Accepted
**Date:** 2026-10-21
**Deciders:** Alex Nodeland

## Context

The UI audit of 2026-10-20 ([lattice RFC-0007](../../rfcs/0007-portalr-brand-kits.md)) found four small things at the edges of the frame. When the skip link was focused it slid down over the mark. The rail had no test holding it in the window. Selected text and the scrollbars used the browser's colours, not the kit's. And below `lg` the pinned header covered whatever a link or the keyboard scrolled to. This is polish PR 6 of the audit.

## Decision

- **The skip link takes its own room.** It is hidden from sight until focused. Focused, it is a bar across the top of the frame (`col-span-full`) that pushes the frame down rather than lying over the mark. It is still the first stop and still leads to `#main`. Leaving it gives the room back. It is security chrome, which no kit restyles.
  - From `lg`, at the top of the page, the bar moves the rail down too. The rail is the window's height, so while the bar shows, the rail's foot sits below the window by the bar's height (about 36px), and the account at its foot is cut off. This is not compensated: the bar shows only between the first Tab and the next, and any scroll pins the rail to the top again. A test records it.
- **The rail stays in the window.** From `lg` the header is a rail the height of the window, pinned at the top while the page scrolls past it. It already behaved this way; a test now holds it. Its width is a kit token, `--rail-width` (15.5rem, as before), so the literal leaves the literal-value list.
- **Selection is a deeper wash.** `::selection` is `--selection`, mixed in base.css as 22% accent over paper (the wash is 10%), so a selection still shows over a washed row. Selected text is `--fg`. The pair `fg` on `selection` (4.5) is in the manifest, and the validator mixes `--selection` as base.css does.
- **Scrollbars take the kit's colours.** The root's `scrollbar-color` is `--edge` on `--paper`. The thumb is a control, so it must hold 3:1. The pair `edge` on `paper` (3) is already in the manifest, and its reason now names the thumb. `--line` was about 1.4:1 in the default light scheme.
- **A scroll stops below the pinned header.** Below `lg`, the root's `scroll-padding-top` is `--header-clearance`, a new kit token (3.5rem, more than the header's height). It applies only where the frame's header is on the page (`html:has([data-frame-header])`). At `lg` the header is beside the page, and a page without the frame has nothing pinned, so the padding is 0 for both.

## Forced colours and overlay scrollbars

- Under forced colours, the browser replaces both `::selection`'s colours and `scrollbar-color` with the system's. Neither is set again for that mode.
- **macOS overlay scrollbars:** checked in Chrome 155 on macOS with overlay scrollbars. Setting `scrollbar-color` didn't add a gutter: the page's scrollbar width was 0px with it and without it, so the scrollbar stays an overlay and only its colours change. Other browsers, or the "always show scrollbars" setting, may draw a classic scrollbar in these colours. That doesn't change the layout either, because the classic scrollbar takes its gutter whatever its colour.

## Consequences

- Easier: a focused skip link no longer hides the mark. Following a link to an anchor on a phone no longer lands the target under the header.
- A kit that sets a much taller header needs `--header-clearance` to match. A test checks the default against the header's real height.
- The computed-style gate's change is only the skip link's line in each scene with a frame. No other scene moves.
