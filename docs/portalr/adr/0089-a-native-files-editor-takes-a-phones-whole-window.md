# ADR-0089: A native file's editor takes a phone's whole window

**Status:** Accepted
**Date:** 2026-10-28
**Deciders:** Alex Nodeland
**Amends:** [ADR-0055](0055-every-kind-inline-and-a-native-file-read-and-edited-in-its-thread.md) (where the editor is framed on a phone)

## Context

On a phone, "Edit in WordCraft" (and the other crafts) turned the file's box in the thread into the editor's frame: the thread column's width less the page's gutters, at most 80% of the window's height, under the file's header and controls (#1060). The craft builds (WordCraft 0.11.0, DeckCraft 0.7.0, GridCraft 0.8.0, as `scripts/craft APP web` fetches them) each declare `width=device-width, initial-scale=1, user-scalable=no` and draw their interface on a canvas. Inside a frame that meta has no effect: the width a framed document lays out for is the frame's box, so a desktop interface was packed into a small box. The shim (artifactr files ADR-0010) fills its own frame and passes the size through, and needs no meta of its own either. Zoom is the host page's: the app's `index.html` declares `width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content` and doesn't forbid it, so a pinch zooms the whole page, frame and bar together, not the editor alone.

## Decision

- **The whole window, on a phone.** Where the editor opens on a phone (48rem and below with a coarse pointer, ADR-0082's variant), `EditorFrame` is drawn in the kit's `WholeDialog`: the frame is the window's width and the rest of its height in CSS pixels, which is the viewport the editor lays out for. The dialog covers the tab bar while it is open, as the diagram's canvas does, and keeps the safe areas clear (the notch, the home indicator, the sides), now in `WholeDialog` itself.
- **A slim bar.** The file's name, and "Back": a plain button, or, with unsaved changes, the same confirmation as "Back to preview". Escape goes back too, except with unsaved changes or while a save is checked in: then it does nothing, since a key meant for the editor shouldn't lose its work, and "Back" asks first.
- **Nothing hidden.** Under the bar: the check-out's state (opening, open, unsaved, checking in, failed), what was last said of the file (a refusal, an export not checked in, an extension refused), which the page beneath can't show, and "Open in its own tab".
- **Its own tab.** The editor's address for the origin the page is at (ADR-0084's aliases, so a phone on the tailnet gets the tailnet one), opened with `noopener noreferrer`: an escape hatch for an editor with no layout for a phone. That tab has no bridge: the file is downloaded and checked in by hand there.
- **Chosen once.** Whether it takes the window is read as it opens and kept: turning the phone past 48rem doesn't move the frame, which would load it again and lose the work in it.
- **The frame is unchanged:** the same shim, `sandbox`, `allow` and origin checks (ADR-0051).

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Where | **`WholeDialog` over the page (chosen)** | Reuses the kit's full view, focus kept, the frame at window size | Covers the tab bar while editing |
| | The box in the thread, taller | No new view | Still the column's width, under the page's chrome |
| The editor's size | **The frame's CSS box (chosen)** | Is what a framed document's viewport is | A desktop-only build still lays out its desktop interface at phone width |
| | A wider frame, scaled down | A desktop layout as designed | Small again: what #1060 reports |

## Consequences

- Easier: editing a document on a phone at a readable size; what is said of a save stays in sight, and on the page once the window closes.
- Usability: where an editor has no narrow layout, it lays out its desktop interface at the phone's width; pinch-zoom enlarges the whole page, bar included, and the editor's own zoom controls, where it has them, are the better way in.
- Known limit, the keyboard: the window is the layout viewport's (`inset-0`), and iOS Safari ignores `interactive-widget`, so the on-screen keyboard can cover the bottom of the frame, and the editor's caret with it, unless the editor scrolls it into view. Following `visualViewport` was left out for its bytes; it is the next step if it bites.
- Known limit, going back: the window adds no history entry. A browser back, or iOS's edge swipe, leaves the thread: with unsaved changes the page asks first (`useBlocker`, as before); without, the editor closes with the page.
- Harder: whether the builds have a narrow layout is the crafts' (WordCraft's build names a mobile layout; DeckCraft's and GridCraft's don't appear to): where they don't, "Open in its own tab" is the way out, without the bridge.
- Size: the files add-on grows by about 200 bytes, and the initial chunk by about 50 (`WholeDialog`, now shared).

## Action items

1. [x] `EditorFrame` in `WholeDialog` on a phone; `WholeDialog`'s `bar` and safe areas; phone tests (light and dark: axe, Escape, focus back on the preview, the frame kept across a turn, a check-in said on the page).
2. [ ] Ask each craft for a narrow layout (WordCraft, DeckCraft, GridCraft).
