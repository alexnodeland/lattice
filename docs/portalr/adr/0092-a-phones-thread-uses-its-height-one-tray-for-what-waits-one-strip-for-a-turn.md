# ADR-0092: A phone's thread uses its height: one tray for what waits, one strip for a turn

**Status:** Accepted
**Date:** 2026-10-29
**Deciders:** Alex Nodeland
**Amends:** [ADR-0082](0082-sheets-the-thumb-bar-and-a-phone-s-tables.md) (the sheet's handle; the thumb bar and the tray), [ADR-0083](0083-a-turn-shows-its-progress-phase-thinking-and-an-estimated-count.md) (what shows that a turn works), [ADR-0085](0085-polish-one-shape-per-part-and-what-is-folded.md) (the strip's tokens are no longer folded), [ADR-0089](0089-a-native-files-proposal-says-what-it-does-in-its-thread.md) (where a proposal sits, open and decided)

## Context

The owner read the thread on an iPhone, over Tailscale, in the dark theme, and found its height badly spent and its parts unsteady:

- The strip over a turn at work was a card of three lines (a spinning badge, a line of phase and clock, a "Tokens" fold that opened to chips wrapping "default" onto a line of its own), with Stop beside them. Three dots pulsed in the thread as well, saying the same.
- A sheet's handle was a 44px band, overlapping padding that was already 20px, around a 40px bar.
- Proposals were cards at the foot of the thread, after the messages, open and decided alike: an accepted proposal kept the room of a card to say "Accepted". A question the agent asked sat in the log above them, so two boxes, neither docked, stood between the reader and the composer.
- The agent's words before a tool call were drawn at 45% opacity, as "not the reply", and read grey: below the contrast text needs (AA). The client marks them (`reply: "stale"`, set when a tool call's part starts after text), and `Streaming` faded the bubble on it; a turn that failed or was stopped faded its whole row on `ended`.
- A run's calls were one line cut by an ellipsis mid-phrase ("Used a tool, looked up commands, edited a file, archived an art…").
- The palette's groups, listed in a `fieldset` (whose minimum width is its content's) inside a box that scrolled up and down (which makes its sideways overflow `auto` too), were as wide as the longest title: a bar to scroll above the field, rows cut at the left, the list dragged to either side.

## Decision

- **The strip is the one sign that the agent works.** The dots in the thread are gone. A turn that has said nothing yet draws nothing; its thinking, once it starts, is folded as before and streams into its fold as it arrives, and its words stream in a bubble. The strip is one line, a dot that breathes (a still dot where motion is reduced, a shape and a word either way), "Working", what it does, the clock in digits of one width and Stop, with a second line for its tokens: "in 32,369 · out 6,925 · reasoning 4,955 · default", one line cut where it is long, there from the first, named in full for a screen reader. Nothing is folded under "Tokens", which amends [ADR-0085](0085-polish-one-shape-per-part-and-what-is-folded.md): one line is less than a fold. The strip rises in, and what it says changes with a fade, not where motion is reduced.
- **What the agent wrote is never faded.** Words before a tool call, and what a stopped or failed turn kept, are drawn as any message's are. The client's `stale` mark stays, for the one place it matters, the posted reply replacing the text.
- **What waits for the reader is one tray, docked with the composer.** Open proposals, questions the agent asks (`ask_user`) and forms it asks for (`ask_form`) are in a tray above the composer, in the dock, so they are never scrolled away and are one box:
  - one waiting is shown whole; several are one line, counted ("2 waiting for you", with what they are), opening to all of them, where a link to one of them (a created file's "changes are waiting for your review") opens it;
  - it scrolls inside itself past 40% of the window less the keyboard's room, and moves nothing sideways;
  - an approval stays as [ADR-0087](0087-a-command-first-layout-a-top-bar-a-palette-a-table-and-a-split-view.md) has it, holding the window's foot over the thread with the dock in the flow under it, its own card and its own reason.
- **What was decided is a line of the thread.** An accepted or rejected proposal is one line, the mark and its title, after the last entry of the run that made it (the thread's last where none did, as the store gives a proposal no place of its own); it is no card and has no part in the tray. Open, a proposal is [ADR-0089](0089-a-native-files-proposal-says-what-it-does-in-its-thread.md)'s card, with what it does in words and Compare as [ADR-0091](0091-a-native-files-proposal-opens-on-its-first-changed-page.md) has it, unchanged.
- **The thumb bar** ([ADR-0082](0082-sheets-the-thumb-bar-and-a-phone-s-tables.md)) still offers a question's next step in the composer's row, but gives way while the card's own button is in view in the tray as well as the window, and stands in where the tray scrolls it away or is closed.
- **A sheet's handle is a pill, 36 by 4px**, in a band 20px tall, the sheet's top padding 8px: the header costs what it holds.
- **A run's calls are said by their kinds, counted, as the owner reads them** ("Made 2 artifacts, used 3 tools, made an app"), in the order first called. Where that doesn't fit a phone's line, the first two kinds if they fit, else the first, are kept whole and the calls of the rest counted: "Made 2 artifacts, used 3 tools and 1 more". A phrase is never cut; the sheet it opens, the line's name, and the desktop's line say all of it. What a line holds is a count of characters, less a failure's share.
- **Nothing in a sheet or a tray moves sideways.** A sheet scrolls up and down alone (`overflow: hidden auto`), the palette's groups may be narrower than their content, and a long title is cut with an ellipsis. A test opens the palette, the calls' sheet and a call's detail, and the Add sheet, with titles and code far wider than the window, and asserts that none scrolls or can be scrolled sideways (but a code block's own box, which the keyboard reaches), and the page is never wider than the window.
- **The rest of the thread is tighter on a phone:** the gaps between messages and between the thread's parts, a card's padding, a composer that starts one line tall, a created file's card that says where its page is in the line it says it was created empty in.

## Options considered

### Option A: One tray in the dock; decided proposals as lines (chosen)

**Pros:** What needs the reader is in one place, at the thumb, never scrolled away; what doesn't is a line.
**Cons:** The dock is taller while something waits (at most 40% of the window for it), and a long card scrolls inside it.

### Option B: Stack the cards in the thread, sticky

**Cons:** Two sticky boxes cover the thread, and decided cards still take a card's room.

### Option C: Several waiting open, none closed

**Cons:** A question and a proposal together fill the window, and a phone's composer, the one thing it is for, is left a strip.

## Consequences

- `Tray`, `ProposalLine` and `proposalTitle` are in `ui`; `threadLog` takes the decided proposals and places them; the thread's page builds the tray's list.
- A question's card is no longer in the log while it waits, but in the tray; its id, its focus and the thumb bar's target are the same.
- The streaming add-on loses its chips; the app's initial and total budgets are met by 78 and 89 bytes, no ceiling raised ([ADR-0040](0040-scenarios-against-a-generated-application-and-size-budgets.md)).
- The screenshot baselines of `ui` change for the strip, the handle and the message list; they are taken from CI's `ui-screenshots` artifact ([ADR-0019](0019-the-kits-look.md)).
