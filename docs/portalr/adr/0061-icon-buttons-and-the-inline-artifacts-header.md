# ADR-0061: Icon buttons, and the inline artifact's header

**Status:** Proposed
**Date:** 2026-10-21
**Deciders:** Alex Nodeland

## Context

The UI audit of 2026-10-20 found row actions outshouting what they act on. Each message had an outlined "Helpful" and "Not helpful" button, and so did each run in a runs table. The inline artifact card stacked four idioms: a kind and a name, an outlined "Full view" button, what the artifact draws, and an underlined "Open its page" link under it. The outline came from a caller's class string (`border-line px-2 py-1 text-xs`) on a ghost button, not from the kit.

## Decision

- **`IconButton` is an action named by its icon.** It is a quiet, ghost square, `--icon-button-size` (32px) across, so it is a target of 24px or more. It is named by `label`, which a tooltip (Base UI's) shows when the pointer rests on it or the keyboard reaches it. A pressed one takes the wash, as a pressed button does. A disabled one keeps its name but is not a stop for the keyboard, so its tooltip is out of reach while it is disabled; feedback is disabled only while it is being sent. Given a `render` element, such as the router's link, it is that link in the button's look (`buttonLook`), named by the label over whatever the element was named; a link takes no button props, which the type says.
- **A tap on a touch screen doesn't show the tooltip.** Base UI's opens on hover and on focus from the keyboard. On a touch screen an icon button is its icon and, for a screen reader, its name. So an icon button is used only for icons people know (thumbs, a page, full screen), and an action whose icon isn't plain is a `Button` with its words.
- **The tooltip is above a full view** (`--tooltip-layer`, 60, over the full view's 50), and Escape closes the tooltip and the full view together: Base UI's tooltip lets Escape go on, and the full view leaves on an Escape that its own back button's tooltip took. Its distance from what it names is 6px, a constant Base UI's positioner takes as a number, not a token; it has no motion of its own.
- **Tokens:** `--icon-button-size`, `--icon-button-radius` and `--icon-button-icon`, and the tooltip's `--tooltip-pad-x`, `--tooltip-pad-y`, `--tooltip-radius`, `--tooltip-shadow` and `--tooltip-layer`.
- **Feedback is two icon buttons,** thumbs up and down, named "Helpful" and "Not helpful", pressed for the one given. The words are in their names and their tooltips, not on the page.
- **The inline artifact's header holds its actions:** its kind and name at the start, and at the end "Open its page" (an icon link) and "Full view" (an icon button). `open` becomes the link element itself (`ReactElement`), drawn in the header, or under the card for an app, which has no header. In the full view the header keeps "Back to the page" only.
- **Not changed:** the mini app's own chrome (`on-demand/apps.tsx`), its label and its button, which is security chrome (lattice RFC-0007); and text buttons such as a code block's "Copy" and "Wrap", whose words are short and clearer than an icon.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Feedback | **Icon buttons with tooltips (chosen)** | Quiet beside what they act on | The words are a hover or a keyboard focus away, and a tap on a touch screen doesn't show them |
| | Words, unoutlined | Plainly said | Two words a message, every message |
| Inline header | **Actions at the header's end (chosen)** | One place for what can be done | The page link is an icon |
| | A link under the card, as before | Plain | A fourth idiom on every card |

## Consequences

- Easier: an icon-only action is one component, named, with its tooltip and its target size.
- Harder: an icon must be one people know; where it isn't, a `Button` with words is the better choice.
- To revisit: the mini app's chrome, with the chrome tokens of the loader PR.
