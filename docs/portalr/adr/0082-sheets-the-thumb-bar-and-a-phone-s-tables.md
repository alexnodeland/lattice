# ADR-0082: Sheets, the thumb bar, and a phone's tables

**Status:** Accepted
**Date:** 2026-10-27
**Deciders:** Alex Nodeland
**Amends:** [ADR-0080](0080-ink-on-paper-the-products-visual-language.md) (the small screens)

## Context

The design pass ([ADR-0080](0080-ink-on-paper-the-products-visual-language.md), [ADR-0081](0081-plain-a-bright-page-one-colour-and-a-mark-for-what-waits.md)) gave a phone its fundamentals: targets a finger can hit, fields a phone won't zoom, safe areas, nothing wider than the page. It left what floats as it was: a menu, a popover and a dialog placed by the pointer or centred, which a thumb reaches badly and the on-screen keyboard covers; a question far up the thread that must be scrolled back to; tables cut off; and the 44px rules held by reading the stylesheet, since the test browser could not be told its pointer was a finger. The owner asked for the rest, in a pull request of its own, with the app's initial budget untouched.

## Decision

- **What floats sits as a sheet on a phone.** Where the window is narrow and a finger is a pointer (`(max-width: 48rem) and (any-pointer: coarse)`, the `phone:` variant), a dialog, a confirm, a menu, the account menu and a popover sit along the bottom of the window, the full width, rounded at the top, with a handle, sliding up and down (not where motion is reduced), scrolling inside themselves past most of the window's height, keeping the home indicator clear, and keeping their scroll to themselves. Each stays what it was: a dialog with its focus kept in and brought back, closed by Escape and its backdrop; a menu with its items and arrow keys. Admin's toolbar forms open as such a dialog on a phone rather than a card beneath the row. The look is classes alone, in the initial stylesheet, so a mouse pays only for the rules.
- **The drag is loaded when a finger needs it.** The touch module (`on-demand/touch.ts`) holds the sheet's drag, by the handle or from a sheet's top when it isn't scrolled, closing it past a third of its height or on a flick, springing back otherwise, and the on-screen keyboard's inset. It is an add-on chunk, imported the first time a page with a finger opens something that floats, so a mouse never loads it; it is measured under the app's add-ons as `touch` and counts toward neither of the app's own totals, as every add-on does.
- **The keyboard.** The viewport asks the browser to resize the page for the on-screen keyboard (`interactive-widget=resizes-content`); where it doesn't, the touch module keeps `--keyboard-inset` on the root at the height the visual viewport says the keyboard covers, and the composer's dock sits above it, so Send is never under the keyboard or the home indicator.
- **The thumb bar.** On a phone, the active request's primary action, Answer or Approve, sits above the composer within the thumb's reach; its button presses the request's own submit button, so the handlers are the request's, and it is hidden from assistive technology, which reaches the one in the request: one tab stop. Its words follow that button's. In a short window it gives way, so what is pinned never covers most of the page.
- **Tables on a phone.** An item table was already a list of cards on a phone ([ADR-0021](0021-the-areas-on-the-frame-and-what-admin-needs.md)). A table proper scrolls inside its box, its first column pinned as the rest scrolls, with shadows at the edges that are scrolled past, drawn by the stylesheet alone.
- **A finger measured.** The kit's tests gain a `touch` project: Chromium as a phone (a finger, a narrow window, twice the scale), running the `*.touch.test.tsx` files alone, so the 44px floor, the 16px fields and the sheets are measured, not read from the rules. Where any pointer is coarse (`any-pointer`, so a touch laptop with a mouse plugged in counts), admin's compact rows reach 44px too and hold at 36px for a mouse alone. The app's and admin's own routes are held never wider than the page at 320, 360, 390, 430 and 768.
- **Not done, and why.** Swiping a thread's row for its actions is not built: it costs a gesture layer and a menu mirror for what a long press and the row's menu already give. A real device is still not in the loop: emulation stands in for it.

## Consequences

- The app's initial chunk carries the sheet classes and the thumb bar; the drag and the keyboard inset are an add-on. The budget's add-on line for `touch` is new; the app's own ceilings are unchanged.
- Every floating surface's screenshot moves on a phone; the desktop baselines don't.
- A kit of its own gets the sheets through the same classes, as they take the kit's radii and shadow.
