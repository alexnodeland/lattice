# ADR-0061: Icon buttons, and the inline artifact's header

**Status:** Proposed
**Date:** 2026-10-21
**Deciders:** Alex Nodeland

## Context

The UI audit of 2026-10-20 found row actions outshouting what they act on. Each message had an outlined "Helpful" and "Not helpful" button, and so did each run in a runs table. The inline artifact card stacked four idioms: a kind and a name, an outlined "Full view" button, what the artifact draws, and an underlined "Open its page" link under it. The outline came from a caller's class string (`border-line px-2 py-1 text-xs`) on a ghost button, not from the kit.

## Decision

- **`IconButton` is an action named by its icon.** It is a quiet, ghost square, `--icon-button-size` (32px) across, so it is a target of 24px or more. It is named by `label`, which a tooltip (Base UI's) shows when the pointer rests on it or the keyboard reaches it. A pressed one takes the wash, as a pressed button does. Given a `render` element, such as the router's link, it is that link in the same look.
- **Tokens:** `--icon-button-size`, `--icon-button-radius` and `--icon-button-icon`, and the tooltip's `--tooltip-pad-x`, `--tooltip-pad-y`, `--tooltip-radius` and `--tooltip-shadow`.
- **Feedback is two icon buttons,** thumbs up and down, named "Helpful" and "Not helpful", pressed for the one given. The words are in their names and their tooltips, not on the page.
- **The inline artifact's header holds its actions:** its kind and name at the start, and at the end "Open its page" (an icon link) and "Full view" (an icon button). `open` becomes the link element itself (`ReactElement`), drawn in the header, or under the card for an app, which has no header. In the full view the header keeps "Back to the page" only.
- **Not changed:** the mini app's own chrome (`on-demand/apps.tsx`), its label and its button, which is security chrome (lattice RFC-0007); and text buttons such as a code block's "Copy" and "Wrap", whose words are short and clearer than an icon.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Feedback | **Icon buttons with tooltips (chosen)** | Quiet beside what they act on | The words are a hover or a focus away |
| | Words, unoutlined | Plainly said | Two words a message, every message |
| Inline header | **Actions at the header's end (chosen)** | One place for what can be done | The page link is an icon |
| | A link under the card, as before | Plain | A fourth idiom on every card |

## Consequences

- Easier: an icon-only action is one component, named, with its tooltip and its target size.
- Harder: an icon must be one people know; where it isn't, a `Button` with words is the better choice.
- To revisit: the mini app's chrome, with the chrome tokens of the loader PR.
