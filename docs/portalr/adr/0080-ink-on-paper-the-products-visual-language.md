# ADR-0080: Ink on paper, the product's visual language

**Status:** Accepted, amended by [ADR-0081](0081-plain-a-bright-page-one-colour-and-a-mark-for-what-waits.md) (the rule, the shape, the badges, the rail's current area, the message grammar, the rhythm)
**Date:** 2026-10-26
**Deciders:** Alex Nodeland
**Amends:** [ADR-0019](0019-the-kits-look.md) (the paper, the edges, the raised surfaces), [ADR-0039](0039-elevation-status-colour-states-and-density.md) (elevation and the badge's pill), [ADR-0053](0053-the-chats-questions-tool-calls-sides-failures-and-streaming.md) (the bubble) and [ADR-0062](0062-badges-and-headings.md) (the badge's shape)

## Context

The owner read the first design pass ([ADR-0079](0079-interaction-states-feedback-pending-and-a-refusals-mark.md)) and said the UIs still looked like Windows Vista, then that the look should be the product's own all the way down: real buttons, real tables, rows as components, no navigation as underlined text, icons of its own, one aesthetic across the app and admin. This record holds the visual language; ADR-0079 holds the states.

## What read as dated

The owner read the first pass and said the UIs still looked like Windows Vista. Read again for that, with the tokens beside the screens, the look came from five things, none of them a component's:

- **A lavender paper.** `--paper` was `#f7f4fb` in light and `#17111f` in dark, a tint of the violet, so every page sat on a violet pane with white cards on it: the tinted glass of that era. Three more tints of the same violet shared each screen: the current nav item's wash, the reader's message bubble, the switcher's chip.
- **Violet-grey chrome.** `--edge`, a control's boundary, was `#857a97`, and `--line` `#dcd5e6`: fields, secondary buttons, the switcher and the upload zone (a 2px dashed edge) were boxed in a purple grey, which reads as window chrome.
- **Stacked elevation.** A card had both a hairline and a shadow, and the shadow was cast in violet (`#281446` at 16%); dialogs and popovers stacked two shadows of it.
- **Pills.** Badges were full-radius pills with coloured edges; the nav's count and "Waiting for you" were solid violet pills; a message bubble had 16px corners and a tail.
- **A bordered switcher.** The workspace switcher was a bordered, paper-filled combobox inside the surface rail.

Gradients, bevels, gloss and inner highlights there were none; the type (Schibsted Grotesk, Fragment Mono) was current. The icons were Lucide's, a pack, which the owner then asked to be the kit's own.

## The direction: ink on paper

A neutral paper with no violet in it, `#f6f6f8` and `#121216`; surfaces told apart by hairlines (`#e3e3e8`, `#2b2b33`) and spacing, a card's shadow a whisper (1px at 8% of a neutral) and elevation kept for what floats; a neutral control edge (`#80808a`, `#75757f`) that still holds 3:1 on every surface; the violet kept as the one accent, for the primary action, links, the focus ring and the current place, so a screen carries one tint where it carried four; crisp radii, 6px on controls and 8px on cards as before, 12px on a bubble (from 16) and 4px on a badge (from a pill); and a dark scheme designed on the same neutrals, with the accent a lighter violet (`#d9bff3`) that reads 4.5:1 on its surfaces. The switcher is a bare trigger, as the header's others are, and the upload zone is a 1px dashed card. The example kits, nightshade and calm, set their own colours and keep their character; the inventory, the schema and the validator are unchanged, and every pair in the manifest holds in both schemes.

## Decisions the code cites

- **The icons are the kit's own** (`icons.ts`): 54 glyphs, each one path on a 16-unit grid, drawn for this product to that grid and the kit's metaphors (a message is a note with a folded corner, a file a leaf with a turned corner, a run a triangle, a rule a bolt), stroked by `Icon` at 1.5 units with round terminals and joins, in the text's colour; arrowheads are short and open at 90 degrees, chevrons the same angle with no curve, every frame half a unit in from the grid's edge. Measured against the pack the UIs used before (sampled-point mean and Hausdorff distance, in units of the 16-grid, the table in the pull request): the primitives are near any set's by construction and are said so rather than claimed away: plus 0.02, x 0.09, info 0.16, circle 0.17, the bang in a ring 0.17, the arrows 0.35, the chevrons 0.36, the thumbs 0.38, workflow 0.41, menu 0.46, check 0.49; everything else is 0.5 or further, most of it past 0.8.
- **A way on that is an action is a `ButtonLink`**: an anchor, the router's `Link` through `render`, in the button's look, so it opens in a new tab and reads as a link; it has no disabled state, as a link hasn't; `aria-current="page"` on one marks it as the current place by weight and a rule, as a nav link is; the census counts it with the buttons by `data-button`.
- **An inline link keeps a rule under it**: the browser's underline, recoloured to the kit's edge at rest and the working colour when hovered, with the kit's offset; it is the one cue beside colour that it is a link in running text, so the edge holds 3:1 on the paper and the surface in both schemes.
- **A subtle link is the text's weight with no underline**, for an id or a name standing alone in a cell; never in running text. A row's link is a row (its chevron says it opens); the places above a page are crumbs with the kit's chevron between them, not underlined words.

## Built and planned

Built in the pull request that adds this record: the neutral kit (paper, hairlines, edges, elevation, radii, dark), the icons, ButtonLink and the links, the crumb trail, rows as a bounded list with a chevron, the table's header and figures, the rail unboxed with the start rule, quiet badges, the flat segmented track, the cards' start rule, the 3xl title and the 64rem measure, the fade in place of the turn; and, as the owner approved, the interactions: the stepped question sets, tool calls grouped per run, the attach button in the composer, admin's forms behind a line and its folding filter bars, revisions one open at a time, the artifact page's overflow menu, long messages folded, the run status strip, composer-first new threads, the needs-you list, jump to latest, the thread's mode switch, message actions as the pointer rests or as a menu a long press opens, thread search with the view in the URL and the moved-since mark, and connecting again without a reload. The small screens below are built here too, but their sheets and the thumb bar in a pull request stacked on this one.

## The language, part by part

*Superseded in part by [ADR-0081](0081-plain-a-bright-page-one-colour-and-a-mark-for-what-waits.md): the rule, the shape, the badges, the rail's current area, the message grammar and the rhythm below are as this record decided them; Plain moved each, and says where.*

The owner then asked for more than a restyle: components of the product's own all the way down, no navigation as underlined text, real buttons and tables, icons that are ours, one aesthetic across the app and admin. These are the rules the kit's components follow; a kit of its own re-skins them through the same tokens.

- **Paper and ink.** One neutral paper, one surface, hairlines between things. The violet is ink: the primary action, links, the focus ring and the current place take it, and nothing else is filled with it. A tint of it, the wash, is a hover or a chosen state, never a surface at rest.
- **The rule.** What waits on the reader carries a rule in the working colour at its start: 4px on an asking card and an approval (`ASKING`, in `states.ts`), 2px on the current area in the rail and a current button link (`before:w-0.5`). It is the alert's left edge generalised, and the one decoration the language has.
- **Shape.** Radii from the kit's scale: 6px on controls, 8px on cards, dialogs and lists, 12px on a message bubble, 4px on a badge, a chip and a count. No pills.
- **Buttons.** `Button` in primary (ink), secondary (hairline), ghost, danger-soft and danger, two sizes, every one 24px or taller with the one ring (a checkbox is 16px and a switch 20px tall on their own: their label is the target, and to a finger every control reaches 44px, below); `IconButton` for an action named by its icon, with a tooltip; `ButtonLink` for a way on that is an action, an anchor in the button's look, which the census counts with the buttons. A small ghost or secondary button is a row's action.
- **Links.** Inline, in running text, in the working colour with a quiet rule under it that takes the working colour when hovered, never the browser's underline; external, the same with the kit's mark; subtle, an id standing alone, in the text's weight with no underline. Nothing else is a text link: a row is a row, a crumb a crumb, a way on a button.
- **Rows.** A list is bounded on the surface with the table's corners, its rows told apart by hairlines; a row has its name, a quieter line beneath, and an end; a row that opens has no underline and the kit's chevron at its end. The whole row is the pointer's target.
- **Tables.** On the surface, bounded; column headers small, quiet, in capitals, on the paper (not pinned: a table scrolls with the page, and pinning the header is a follow-up with a scrolling box of its own); a column of figures sits at the end on its digits; rows wash on hover; row actions are small buttons in the last column; admin's compact density stays. An item table is cards on a phone.
- **Tabs and segments.** A tab bar is a hairline with the current tab underlined in the ink; a segmented filter is a flat track on the line with the chosen segment raised on the surface in the text's weight.
- **Badges.** A status badge is a quiet hairline badge whose mark carries the colour (ADR-0039's shapes); only waiting for you is on the wash in the ink. A badge that says what a thing is is quiet, or on the wash for the one thing the reader is pointed to. A count is a small square badge on the wash.
- **Fields.** A hairline-edged control on the surface with the kit's edge, which holds 3:1 on every surface as a control's boundary must, the ring on focus, the failed colour and mark when refused; labels and hints on the type scale.
- **Menus, popovers and dialogs.** One surface, one neutral shadow, 8px corners, the kit's chevrons and checks; a dialog over a neutral scrim with its title on the type scale.
- **Icons.** The kit's own set (`icons.ts`): 54 glyphs on a 16-unit grid, one path each, stroked 1.5 with round terminals, in the text's colour, drawn for this product (a thread a folded note, an artifact a leaf with a turned corner, a run a triangle, a rule a bolt); no pack.
- **Type.** Schibsted Grotesk and Fragment Mono. The page's title at the kit's 3xl, tight; sections at lg; labels at sm semibold; figures tabular where they line up. The measure is 64rem.
- **Rhythm.** The page's parts 2rem apart; a card's padding 1rem; rows 0.75rem tall-padded.
- **Elevation.** A card casts a whisper; what floats, a menu, a tooltip, a dialog, casts the kit's shadow; the rail and the header cast nothing and are set apart by space alone.
- **Motion.** Every control answers the pointer over the feedback tokens; what opens fades; nothing turns; reduced motion stops all of it.
- **Dark.** Designed on the same neutrals, with the kit's own lighter violet as the accent while the marks keep lattice's ink.

The style census counts 10 link looks (from 12) and 4 badge looks (from 6); Biome's raw-element list has 2 files (from 3).

## Small screens

*Amended by [ADR-0082](0082-sheets-the-thumb-bar-and-a-phone-s-tables.md): what floats becomes a sheet on a phone, the thumb bar, a phone's tables, the keyboard, and a finger measured in the tests.*

A phone is a first target, not a narrowing of the desktop. The fundamentals are in the kit's base styles and the shell, so every page has them:

- **A finger's targets.** Two media questions, each for its own concern: `pointer: coarse` says the pointer is imprecise, so every control is 44px or taller to it; `hover: none` says nothing can rest on a control, so nothing waits on a hover (the message's actions). A phone answers both; a touch laptop answers the first with a mouse plugged in and keeps its hover. Where the pointer is coarse, every control is 44px or taller: the icon button, a disclosure's line, a crumb, a table row, the header's trigger, and every button, select and text input by a floor on their height. Admin's compact density holds for a mouse and gives way to the same floor for a finger.
- **Fields a phone won't zoom.** A field's text is 16px to a finger, so iOS keeps the page where it is when one is focused. The composer's keyboard offers Send; the search field's offers Search; the sign-in's fields say what they are for autofill.
- **A tap answers at once.** No tap flash of the browser's (the kit's feedback is the answer), and no double-tap zoom on a control (`touch-action: manipulation`).
- **No hover-only path.** What a hover reveals, a message's actions, is on the surface to a finger as a menu, which a long press on the message opens too; the keyboard reaches everything either way.
- **Safe areas.** The viewport reaches the screen's edges (`viewport-fit=cover`); the page keeps the sides clear, the header pinned to the top keeps the notch clear itself (its padding, and the room a scroll stops below), the composer's dock keeps the home indicator clear, and the drawer, which stands over the page, keeps the top, the bottom and its own side clear.
- **Short windows.** The composer pinned to the bottom gives way to the flow under 30rem of height, as on a phone turned on its side or at a high zoom, so it never covers most of the page; Jump to latest returns the reader to the end.
- **Nothing wider than the page.** At 320 and 360 nothing widens the page: a long unbroken word wraps in a message, a code block, a table and a preview scroll inside their own box, and a part that scrolls inside keeps its scroll to itself (`overscroll-behavior: contain`): a scroll that reaches its end stops there, rather than going on to the page or pulling it down to refresh. A test holds this for the thread's parts at both widths.
- **Still to come, stacked on this pull request:** menus, popovers and dialogs as bottom sheets on a phone (loaded on first open, not in the first paint), the active request's action in a thumb bar above the composer, tables as stacked rows, swipe on a thread's row, the on-screen keyboard kept clear of the composer, and the full emulated evidence.

## Consequences

- Easier: every page inherits the look from the default kit's tokens and the kit's components; a kit of its own re-skins the same anatomy.
- A deployment on the default kit changes colour. The kit contract holds; the inventory gains two rows (`component.feedback.duration` and `.ease`) and a size (`font.size.3xl`), the schema and the example kits follow, and the validator's rules are unchanged but for the selection's share, 22% to 30%, which base.css mixes the same way (`test_brand_kit.py` holds both).
- Every screenshot baseline moves with the paper, and the computed-style snapshots with every colour.
