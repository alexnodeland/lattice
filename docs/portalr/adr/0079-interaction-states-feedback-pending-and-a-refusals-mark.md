# ADR-0079: Interaction states: feedback, pending, and a refusal's mark

**Status:** Accepted
**Date:** 2026-10-26
**Deciders:** Alex Nodeland
**Amends:** [ADR-0037](0037-form-controls-and-row-actions.md) (a field's refusal), [ADR-0053](0053-the-chats-questions-tool-calls-sides-failures-and-streaming.md) (the composer) and [ADR-0068](0068-where-the-focus-goes-and-one-not-found.md) (a download keeps the focus, now every command)

## Context

A design pass of 2026-10-26 read the app and admin against the kit for consistency, depth of interaction and finish, after the polish PRs (ADR-0059 to ADR-0068) had put every look on the kit's variants. What it found was not looks but states, the part of a control the census doesn't count (ADR-0066):

- **Feedback was a button's alone.** A `Button`'s colours change over `--button-duration`; a nav link, a tab, a text link, a row, a field, a check, a switch, a segment, a select's trigger and the header's triggers changed at once. Two controls side by side answered the pointer differently.
- **Pending dropped the focus.** ADR-0068 kept the focus on a download while it went; 24 other buttons still wrote `disabled={pending}`, so Approve, Accept, Answer, Start, Save and Send again each sent the keyboard to the document the moment they were pressed, the fault the audit called S3.
- **A refusal was words alone.** A refused field's edge went to the text's colour, which a reader doesn't take as a fault, and its words under the control carried no mark; an alert, a status badge and a failed run each have one (ADR-0039).
- **The composer was two lines,** whatever was written: a third line scrolled out of sight.
- **One-offs:** the dashboards' sortable column header was a raw `<button>` 16px tall (the audit's N6), on Biome's exception list; a Markdown link had its own underline offset and no focus ring; the dialogs' titles were set by hand beside the type scale; sign-in's button overrode the button's padding; a card in an item table was always an `h3`, under an `h1` on admin's Members, Tenants and Audit (N3); the selection's tint was 1.3:1 from the paper (N8).

## Decision

- **Every control has the same feedback.** `FEEDBACK` in `states.ts` is one transition of colour, background, border and underline colour over `--feedback-duration`, eased by `--feedback-ease`, and none under reduced motion (ADR-0057 holds: both read `--motion-scale`). Links, rows, nav links, tabs, the header's triggers, fields, selects and their items, menu items, checks, switches, segments, a question's options, disclosures and a table's rows take it. A button keeps its own tokens (ADR-0037); the two new tokens default to the same primitives, `--duration-fast` and `--ease-in-out`, and are in the inventory and the default kit. `RING` beside it is the focus ring every control already drew, written once.
- **A button pressed is `pending` until its command settles.** `Button` takes `pending`: it can't be pressed again and takes the disabled look, but stays focusable (Base UI's `focusableWhenDisabled`), so the keyboard stays where it was. `disabled` is for a control that can't be used before it is pressed: a Send with nothing written, a Start before the workspace is live, an Accept that is blocked. Every button that disables itself on its own press is `pending`: the chat's command buttons, Approve and Deny, Accept and Reject, Answer, a form's submit, Start, Save, check-out's, sign-in's. ADR-0068's rule for a download is this one.
- **A refusal has the failed mark.** A refused field's or group's edge is `--status-failed`, the colour a status badge's failed edge is, 3:1 on the paper and the surface as a mark must be; and the words under it start with the failed mark, `CircleAlert` in that colour, hidden from assistive technology, which still hears the words as the control's description. The label and the hint are `TYPE.label` and `TYPE.note`.
- **The composer grows with its lines**, from two to sixteen rem, then scrolls: `field-sizing: content`, no script.
- **Folded onto the kit:** a sortable column's header is the kit's small ghost button, 24px tall, its words set back by the button's own padding so they stay at the column's edge, and the dashboards' add-on leaves Biome's raw-element list; a Markdown link is the kit's inline link (`linkLook`), with its ring; a dialog's title is `TYPE.section` and its description `TYPE.meta`, a whole dialog's title `TYPE.subsection`; a question's words are `TYPE.subsection`; sign-in's button has the button's padding; an item table's card is headed one level under what names the table, `h2` under a caption, `h3` under the heading named, or `level`; the selection is the accent at 30% on the paper, 1.6:1 from it and still 7:1 under the text.

## Consequences

- Easier: a kit sets how every control answers the pointer with two tokens, and a reader who presses a button by the keyboard is still on it when the answer comes.
- Harder: `pending` and `disabled` are two props with one look; a caller says which it means. `focusableWhenDisabled` stays for a control that can't be used yet but should be reached, such as a pager's end.
- The computed-style snapshots move for every control that gained feedback (its `transition-*` lines) and for a refused field's edge and mark; the screenshot baselines move where a refusal, a dialog's title or the selection is in a gallery.
- The style census's counts don't move: a pending button looks disabled, and the sortable header is a ghost button the kit already counts.
- The app's initial size stays under its ceiling (ADR-0040) without raising it; the shared `RING` and `FEEDBACK` strings replace a focus-ring string each control carried.
- Not done here, from the audit's nits: an artifact's window title by its name (N1, ADR-0068's reason holds), a dashboard's repeated landmark names (N4), one status region for a thread's loading files (N5), a tooltip's description (N7) and Share's first focus on its heading (N9).
