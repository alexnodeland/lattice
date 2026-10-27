# ADR-0085: Polish: one shape per part, and what is folded

**Status:** Accepted
**Date:** 2026-10-27
**Deciders:** Alex Nodeland
**Amends:** [ADR-0080](0080-ink-on-paper-the-products-visual-language.md) (the rhythm, the mark in the frame), [ADR-0081](0081-plain-a-bright-page-one-colour-and-a-mark-for-what-waits.md) (counts in mono, a table's head on the wash, an alert's edge), [ADR-0082](0082-sheets-the-thumb-bar-and-a-phone-s-tables.md) (a phone's bar), [ADR-0083](0083-a-turn-shows-its-progress-phase-thinking-and-an-estimated-count.md) (the strip's tokens)

## Context

The owner read the UIs on a phone after Plain and the sheets had landed and said they still looked unfinished (#805). An audit shot every screen at 320, 393, 430, 768, 1024 and 1440 in both schemes and ranked twenty findings. None was a missing component: they were the same part drawn several ways (two content widths per kind of page, three trailing shapes in a row, counts in two faces, actions that wrapped under a title on a phone), bare text where a control belonged (a workspace's areas, "Name it first…"), and what a reader didn't ask for shown first (a rule's JSON, an app's 700-line source, a run's ids, every row's thumbs). The owner approved the audit and decided its open questions.

## Decision

Nine rules, held by the kit's components so every page has them:

1. **Spacing.** The scale is 4, 8, 12, 16, 24, 32. A page's parts are 24px apart on a phone and 32px from the rail (`AppShell`); a component's own gaps are 8 or 12.
2. **One page header.** The places above, then the title with at most a primary button and an overflow icon button on its line, at every width, never wrapped under it; then one muted line (`PageHeader`). A thread's actions are an icon button (`Menu` is an icon button now; its text trigger is gone, as no page used one but the thread's).
3. **Two widths, centred.** A reading page (a thread, an artifact, a rule) is the reading measure centred in the column; a collection (lists, tables) the page width.
4. **One row.** A row's title and its line beneath share a left edge: the unread mark sits in the row's own start padding. Its end is a status mark and word or the chevron, never both. Times are relative, the moment on hover (`Ago`), the Runs table's too.
5. **Fields.** Labels show on forms; a search is the kit's glyph, its words as the placeholder and its name (`SearchField`), on the row of its filters.
6. **Buttons.** One primary per view; nothing navigational is bare text: a workspace's areas are a track of links with their glyphs (`Tracks`, `TrackLink`), words from the small breakpoint; "Name it first…" is a quiet button in the composer's row; a toolbar's buttons are full size, the view's main one primary (Members' Invite); the upload zone is one row, its button the label.
7. **Status.** Always a mark and a word, one signal per failure: an alert's mark is its shape, in its tone's colour, and its edge the hairline all round (no coloured rule beside a coloured icon). A stopped turn ends with the stopped mark and "Stopped", as Runs says it. Working, where motion is reduced, is a whole ring, never a still arc that reads as a "c". Counts are the sans on its digits, never mono.
8. **Folded until asked.** A revision of an artifact opens when asked (none at first, and a new one arriving opens nothing); a document's opens on its Preview. A rule reads as When, Then, For each, Retries, Starts and State, its JSON folded under them. An artifact's id is in its overflow (Copy id), its line "Kind · v2 · 3 hours ago". A failed turn says a short error (one line, 120 characters) in the alert and folds a long one under Details. Which files an upload takes is folded under "Supported files". A turn's tokens are folded under Tokens (see below).
9. **Phone surfaces.** Menus are sheets (ADR-0082); thumbs on Runs show as the pointer rests on a row, and in a phone's row they are its menu, a sheet.

And the owner's decisions on the audit's questions:

- **A workspace's home** is a row per workspace, its name opening its threads, with the track of its five areas.
- **The agent's mode** is a small toggle, "Edits" and "Proposes", a radio group named "Agent mode", in the composer's row beside Attach and Send; the `set_thread_mode` command is unchanged. The thread's header keeps the title and the actions' icon button.
- **The mark.** A phone's bar has none: the menu's glyph, the switcher and the account (the drawer holds the way home). The rail and the drawer set portalr's lockup in the violet alone (`Lockup mono`); signing in keeps its inks. A deployment's own mark is untouched.
- **Thumbs on runs** as above: on hover or focus with a pointer, in the row's menu on a phone.
- **Tokens** are behind a disclosure for everyone: the strip says its status, phase, elapsed time and Stop; "Tokens" opens the chips.
- **Bytes.** The app's initial ceiling isn't raised. What this pays with: Streamdown's classes for the parts portalr turns off (its code and diagram toolbars, the link modal, the diagram's full screen, the download menu) are left out of the stylesheet (`@source not inline`), the dead `Mark` is deleted, and the new looks reuse the kit's classes.

Two of the audit's findings were the fixture's, not the product's: a turn ended by Stop is `stopped`, never `cancelled` (artifactr's `RunEnded`), and an approval's `app` is the server's title ("WordCraft"), so "into your WordCraft" reads right; "the site" was the fixture's.

## Consequences

- Every screenshot baseline and computed-style snapshot of a changed part moves.
- A kit of its own keeps its tokens; the sign-in card's radius and padding hold from the small breakpoint, and a phone shows the form on its gutter.
- Not done: the phone search's collapse behind its glyph (the field wraps to its own row instead), a run's own detail page, and the approval's tick drawn into the card's corner.
