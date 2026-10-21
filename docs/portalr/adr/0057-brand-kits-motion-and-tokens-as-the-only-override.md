# ADR-0057: Brand kits: a motion system with guard rails, and tokens as the only override

**Status:** Proposed
**Date:** 2026-10-20
**Deciders:** Alex Nodeland

## Context

[ADR-0056](0056-brand-kits-token-layers-loading-and-validation.md) puts every component on tokens so a brand kit ([lattice RFC-0007](../../rfcs/0007-portalr-brand-kits.md)) can restyle it. Two questions remain: how far a kit may change motion, which can harm a reader as well as please one, and whether a kit may bring CSS of its own beyond tokens. Today motion is ad hoc: a dialog's fade and scale, a scrim's blur (ADR-0039), placeholders' pulse, each turned off under `prefers-reduced-motion`, each with its own duration in its class string.

## Decision

- **Motion is tokens from a closed set.** Entry and exit patterns (fade, rise, scale, slide from an edge, none), a duration scale and an easing scale, each component naming its pattern by component token (`--dialog-enter`, `--toast-exit` and the rest). Patterns are a loader-owned enum under `$extensions`, not DTCG, expanded into duration, easing, opacity, shift and scale properties. Presets set them as a group: `none`, `subtle` (today's values, the default) and `lively`.
- **Guard rails, held by the validator:** no transition or animation token over 600ms; tokens marked instant (hover and press feedback) at 80ms or less; no loop with a period under 333ms that changes opacity or luminance by more than 10%; shift, lift and slide at most 24px; entry scale from 0.9 to 1 and press scale from 0.95 to 1; easing y values between -0.1 and 1.1.
- **Reduced motion is structural.** Every component multiplies its durations by `--motion-scale` (amended by "As built" below: durations only, not shifts or scale offsets), and loops read `--motion-loop`. Under `prefers-reduced-motion: reduce` the base stylesheet, after `brand.css`, sets `--motion-scale: 0 !important` and `--motion-loop: paused !important`; neither is in the kit's grammar. Infinite animations stop at rest, at their resting opacity, which a test holds, and script-driven motion reads the same query and tokens. A test renders a worst-case kit under reduced motion and asserts every computed transition and animation duration is 0s or paused. A kit that wants no motion anywhere takes the `none` preset.
- **Tokens are the only override in v0.2** (the owner's decision). A kit brings no CSS: no `parts.css`, no selectors, no class names. What a kit can't reach with tokens it can't change. A free-form layer may be proposed for v0.3, with its own review of what it can break.

## As built

The foundation PR (#452): motion's scale multiplies durations, not shifts or scale offsets, since with every duration 0 they move nothing. The guarantee is where durations are declared: every duration token is declared on `:root`, where the scale is already 0 under reduced motion, so an element that declares `--motion-scale` below changes nothing it inherits; a test holds it. `--motion-scale` and `--motion-loop` are base.css's and in no kit's grammar. A placeholder's pulse and a working status's spin are loops, which `--motion-loop` pauses. The thinking dots' stagger is a delay, which a pause holds. `--button-press-scale` and `--button-lift` are not tokens yet: they have no value today.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Motion | **Closed patterns and scales, with guard rails (chosen)** | Every kit's motion is safe to show; validated, not reviewed | A kit can't invent a pattern |
| | Free keyframes | Anything | Unvalidatable; flashing and vestibular harm by mistake |
| Reduced motion | **Structural, `!important` custom properties (chosen)** | A kit can't undo it | A kit can't keep a gentle fade under it |
| | Each kit's own block | Flexible | One kit forgets it |
| Override | **Tokens only (chosen, by the owner)** | Validated; security chrome and screenshots safe | Some looks are out of reach until v0.3 |
| | Tokens and a `parts.css` | Reaches anything | Can restyle the mini app's label or host dialogs; can't be validated |

## Consequences

- Easier: motion is consistent and named; a reader who reduces motion gets it everywhere, whatever the kit.
- Harder: a new transition needs a pattern from the set, or a change to the set and its rails.
- To revisit: a `parts.css` layer in v0.3; whether `lively` earns its place once the motion playground shows it.

## Action items

1. [ ] Foundation PR: motion primitives and component tokens at today's values; the structural reduced-motion block.
2. [ ] Loader PR: the guard rails in the validator.
3. [ ] Tooling PR: the presets and the motion playground.
