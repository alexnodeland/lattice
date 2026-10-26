# ADR-0080: Ink on paper, the product's visual language

**Status:** Accepted
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

Gradients, bevels, gloss and inner highlights there were none; the type (Schibsted Grotesk, Fragment Mono) and the icons (Lucide, 2px) were already current.

## The direction: ink on paper

A neutral paper with no violet in it, `#f6f6f8` and `#121216`; surfaces told apart by hairlines (`#e3e3e8`, `#2b2b33`) and spacing, a card's shadow a whisper (1px at 8% of a neutral) and elevation kept for what floats; a neutral control edge (`#74747f`, `#75757f`) that still holds 3:1 on every surface; the violet kept as the one accent, for the primary action, links, the focus ring and the current place, so a screen carries one tint where it carried four; crisp radii, 6px on controls and 8px on cards as before, 12px on a bubble (from 16) and 4px on a badge (from a pill); and a dark scheme designed on the same neutrals, with the accent a lighter violet (`#d9bff3`) that reads 4.5:1 on its surfaces. The switcher is a bare trigger, as the header's others are, and the upload zone is a 1px dashed card. The example kits, nightshade and calm, set their own colours and keep their character; the inventory, the schema and the validator are unchanged, and every pair in the manifest holds in both schemes.

## The language, part by part

The owner then asked for more than a restyle: components of the product's own all the way down, no navigation as underlined text, real buttons and tables, icons that are ours, one aesthetic across the app and admin. These are the rules the kit's components follow; a kit of its own re-skins them through the same tokens.

- **Paper and ink.** One neutral paper, one surface, hairlines between things. The violet is ink: the primary action, links, the focus ring and the current place take it, and nothing else is filled with it. A tint of it, the wash, is a hover or a chosen state, never a surface at rest.
- **The rule.** What waits on the reader carries a 4px rule in the working colour at its start: an asking card, an approval, the current area in the rail. It is the alert's left edge generalised, and the one decoration the language has.
- **Shape.** Radii from the kit's scale: 6px on controls, 8px on cards, dialogs and lists, 12px on a message bubble, 4px on a badge, a chip and a count. No pills.
- **Buttons.** `Button` in primary (ink), secondary (hairline), ghost, danger-soft and danger, two sizes, every one 24px or taller with the one ring; `IconButton` for an action named by its icon, with a tooltip; `ButtonLink` for a way on that is an action, an anchor in the button's look, which the census counts with the buttons. A small ghost or secondary button is a row's action.
- **Links.** Inline, in running text, in the working colour with a quiet rule under it that takes the working colour when hovered, never the browser's underline; external, the same with the kit's mark; subtle, an id standing alone, in the text's weight with no underline. Nothing else is a text link: a row is a row, a crumb a crumb, a way on a button.
- **Rows.** A list is bounded on the surface with the table's corners, its rows told apart by hairlines; a row has its name, a quieter line beneath, and an end; a row that opens has no underline and the kit's chevron at its end. The whole row is the pointer's target.
- **Tables.** On the surface, bounded; column headers small, quiet, in capitals, on the paper, kept at the top where a table scrolls; a column of figures sits at the end on its digits; rows wash on hover; row actions are small buttons in the last column; admin's compact density stays. An item table is cards on a phone.
- **Tabs and segments.** A tab bar is a hairline with the current tab underlined in the ink; a segmented filter is a flat track on the line with the chosen segment raised on the surface in the text's weight.
- **Badges.** A status badge is a quiet hairline badge whose mark carries the colour (ADR-0039's shapes); only waiting for you is on the wash in the ink. A badge that says what a thing is is quiet, or on the wash for the one thing the reader is pointed to. A count is a small square badge on the wash.
- **Fields.** A hairline-edged control on the surface with the kit's edge, which holds 3:1 on every surface as a control's boundary must, the ring on focus, the failed colour and mark when refused; labels and hints on the type scale.
- **Menus, popovers and dialogs.** One surface, one neutral shadow, 8px corners, the kit's chevrons and checks; a dialog over a neutral scrim with its title on the type scale.
- **Icons.** The kit's own set (`icons.ts`): 53 glyphs on a 16-unit grid, one path each, stroked 1.5 with round terminals, in the text's colour, drawn for this product (a thread a folded note, an artifact a leaf with a turned corner, a run a triangle, a rule a bolt); no pack.
- **Type.** Schibsted Grotesk and Fragment Mono. The page's title at the kit's 3xl, tight; sections at lg; labels at sm semibold; figures tabular where they line up. The measure is 64rem.
- **Rhythm.** The page's parts 2rem apart; a card's padding 1rem; rows 0.75rem tall-padded.
- **Elevation.** A card casts a whisper; what floats, a menu, a tooltip, a dialog, casts the kit's shadow; the rail and the header cast nothing and are set apart by space alone.
- **Motion.** Every control answers the pointer over the feedback tokens; what opens fades; nothing turns; reduced motion stops all of it.
- **Dark.** Designed on the same neutrals, with the kit's own lighter violet as the accent while the marks keep lattice's ink.

The style census counts 10 link looks (from 12) and 4 badge looks (from 6); Biome's raw-element list has 2 files (from 3).

## Consequences

- Easier: every page inherits the look from the default kit's tokens and the kit's components; a kit of its own re-skins the same anatomy.
- A deployment on the default kit changes colour. The kit contract, the inventory's rows, the schema and the validator's rules are unchanged; the validator mixes the selection at the share base.css now uses.
- Every screenshot baseline moves with the paper, and the computed-style snapshots with every colour.
