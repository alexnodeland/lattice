# ADR-0087: A command-first layout: a top bar, a palette, a table and a split view

**Status:** Accepted
**Date:** 2026-10-28
**Deciders:** Alex Nodeland
**Amends:** [ADR-0029](0029-ui-polish-from-the-screenshots.md) (one width rule, the phone's drawer), [ADR-0081](0081-plain-a-bright-page-one-colour-and-a-mark-for-what-waits.md) (the rail's current area, in the app), [ADR-0085](0085-polish-one-shape-per-part-and-what-is-folded.md) (the threads' search, the page header's places above, a provider's error, the layout pass it promised)

## Context

After the polish pass the owner wrote: the threads' search should collapse to an icon, a big plain field that isn't used is poor design; much is superfluous or should be tucked away; the layout is elements stacked one on another; the next pass should use the corners and the whole screen. Three directions were drawn as mockups (a quiet split, command-first, a corner dock) and the owner chose B, command-first, with borrows from the other two.

## Decision

In the app; admin keeps its rail (`RailShell`, the old `AppShell`), whose classes now live in `rail.css`, which admin imports, so the app's stylesheet doesn't carry them.

- **One bar along the top** (`AppShell`), pinned at every width: the mark (from 1024 pixels; a phone's bar has none), the switcher, the workspace's areas as a track (`Tracks`, the current one raised as a chosen segment; open proposals counted on Proposals), and in its end corner the magnifier, what waits for the reader ("2 need you", a link to the threads that wait) and the account. At 360 pixels and under the switcher names the workspace alone (the tenant is in its menu), and on a phone what waits is its count alone, named in full. Below 1024 pixels the areas are the page's first row, in its flow. There is no drawer and no left rail. The bar's current area is the way back up, so the app's pages carry no breadcrumb; `PageHeader` takes a `Breadcrumbs` element where a page has one (admin's trace).
- **Search is a palette** (`app/src/on-demand/palette.tsx`, an add-on of about 1.9 KB loaded the first time it opens, behind the kit's `PaletteFrame`): one field over the workspace's threads and artifacts by title, its areas and New thread, a combobox over one list, opened by the magnifier, by Ctrl+K or ⌘K anywhere, and by "/" outside a field; no key opens it with another modifier held or over a dialog already open. Escape gives the focus back to what opened it (the magnifier, for a key); following a result goes to that page's heading (ADR-0068). The threads page's own search field, its chip and its `q` in the URL are gone; `SearchField` with them. The magnifier is the kit's `search` glyph: the set keeps its 54 glyphs.
- **The threads are a table** from 1024 pixels: Thread, Last message, Status, Active, the unread mark in the row's start padding, Mark as read on hover or focus, and the arrows moving from one thread's link to the next's; rows below 1024. The filter sits in the title's corner (on a phone, the row under it). The Needs you section is folded into the bar's count and the filter. The page is at most 1200 pixels wide, centred, the last message taking the table's spare width. The composer that starts a thread is docked at the page's foot; on a phone (the kit's `phone` variant: 48rem or narrower with a coarse pointer; a mouse at the same width keeps the composer) a band of "Search or go to…" and a primary Start a thread stands in its place until it is pressed, as the palette's New thread does (`#new`).
- **A thread beside its artifact** from 1100 pixels: the thread's latest inline artifact, and any approval waiting, sit in a pane of their own on the right, the approval's card, with Deny and Approve, floating in the pane's bottom corner; that artifact isn't drawn again in the log. Narrower, the thread is one column, and a waiting approval's card holds the window's foot (sticky) with the composer's dock in the flow under it, so Deny and Approve are never off screen or covered; `approval-reach.test.tsx` holds this from 320 to 1440 pixels. A phone's thumb bar still mirrors a question's Answer and Next; for a plain approval it gives way, as it always did to a card in view, since the card is now always in view.
- **The turn's strip above the composer** while the turn works, with Stop, in the composer's dock; while it waits on a question the strip stays above what it asks, where a phone's thumb bar answers it, so the dock keeps its quarter of a small phone's window (ADR-0082).
- **Full width.** ADR-0029's width rule changes: a collection uses the window's width less the gutters (16, 24, then 32 pixels), not the page width; a reading page alone keeps the 760-pixel measure, centred; a thread beside its artifact takes the whole width, in two halves.
- **Session replay.** A page that may be recorded marks itself as a direct child of `main` (no wrapping `div` any more), and every dialog is blocked: the drawer it excepted is gone, and the palette holds the workspace's titles.

And the polish review's follow-ups:

1. The touch message actions' trigger, for a screen reader alone, shows once the keyboard reaches it (`has-focus-visible:not-sr-only`), never an invisible stop.
2. Search gives the focus back on Escape, and "/" ignores Ctrl, ⌘ and Alt and an open dialog (above).
3. `styles.test.ts` scans stylesheets and MDX as well as scripts, and finds a class beside a template's placeholder or in an `@apply`; a class behind a variant is another class, which Tailwind keeps, and isn't counted (`fine:opacity-0` is built while `opacity-0` is left out).
4. A provider's error is said no firmer than its cause: "Nothing was lost" is gone, since what the turn did before it failed stays done; a timeout is the provider's only where the error doesn't name a tool.

## Bytes

The app's initial ceiling isn't raised: the rail's and drawer's classes leave its stylesheet (about 590 bytes), the threads' search, chip and Needs you section go, and `PageHeader` no longer imports `Breadcrumbs`. The palette is the one new add-on, `palette`, with a ceiling of 2,100 bytes (1,864 at the time).

## Not done

A phone's approval as tabs of thread and artifact, which mockup B drew, isn't in the decision: a phone keeps the thumb bar. The tenant's home has no search (it has no workspace stream to search). A 55th glyph: the set's magnifier already serves.

## Consequences

- Every screenshot baseline with the frame moves; admin's do not.
- The app's frame is simpler to test: no drawer, one bar.
- Pull requests open at the same time that add ADR-0086 or touch the thread's page (#828) will meet this one in the queue.
