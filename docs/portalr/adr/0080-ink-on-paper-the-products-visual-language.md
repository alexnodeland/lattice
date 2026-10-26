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

## Consequences

- Easier: every page inherits the look from the default kit's tokens and the kit's components; a kit of its own re-skins the same anatomy.
- A deployment on the default kit changes colour. The kit contract, the inventory's rows, the schema and the validator's rules are unchanged; the validator mixes the selection at the share base.css now uses.
- Every screenshot baseline moves with the paper, and the computed-style snapshots with every colour.
