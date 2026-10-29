# ADR-0089: A native file's proposal says what it does, in its thread too

**Status:** Accepted, amended by [ADR-0091](0091-a-native-files-proposal-opens-on-its-first-changed-page.md) (open on the first changed page), and by [ADR-0092](0092-a-thread-uses-its-height-one-tray-for-what-waits-one-strip-for-a-turn.md) (where a proposal sits, open and decided)
**Date:** 2026-10-28
**Deciders:** Alex Nodeland
**Amends:** [ADR-0050](0050-a-native-files-proposals-and-the-pilots-scenarios.md) (what a native file's proposal shows, and where)

## Context

In a thread, a proposal on a native file used the plain `ProposalCard`: its one-line summary, Accept and Reject. `RuleProposal` added nothing for a file. `NativeProposal`, which says how the proposal was made and whether it is outdated, and offers "Compare with version N", appeared only on the proposals page and the file's own page. A reviewer in the thread, where the agent's work is read, had nothing to accept on (issue 1090). [Native files ADR-0020](../../artifactr/files/adr/0020-a-proposal-said-in-words-and-previewed-by-its-own-pages.md) adds what the proposal's commands do, in words.

## Decision

- **The thread renders `NativeProposal` for a proposal on a native file,** chosen by the file's kind (`NATIVE`), as the proposals page does. Any other proposal keeps `ProposalCard` with `RuleProposal`. `NativeProposal` takes the card's `id`, so the created-empty card's link still reaches it. Its parts load with the files add-on, so the thread's own chunk pays only for the choice.
- **An open proposal's card unfolds in levels,** as a run's calls do ([ADR-0053](0053-the-chats-questions-tool-calls-sides-failures-and-streaming.md)):
  1. **The line in words,** in bold under the title: "Adds 6 slides: Title, Itinerary, …". It is read when the card is drawn, except for a check-in, which the patch's provenance says was made by no commands and which shows no line. A read that fails says "Couldn't read what this does. You can still accept or reject it."
  2. **Its changes,** each a line ("Adds a slide: “Itinerary”"), which opens to its arguments in the JSON view, with Copy. When more were made than are listed, the card says "And N more."
  3. **Compare,** as before: the proposal's words and pages beside the head's, read only when asked.
  4. **Its commands, as listed** (long text and server paths cut, at most 200), in the JSON view, with Copy.
- **On a desktop, the line unfurls the changes beneath it** (`aria-expanded`, `aria-controls`). **On a phone, it opens a sheet** (`aria-haspopup="dialog"`, [ADR-0082](0082-sheets-the-thumb-bar-and-a-phone-s-tables.md)), the kit's dialog titled by the line. The sheet lists the changes; one tapped goes on to its arguments, with "Back to the changes" focused, and Back returns the focus to that change's row. Closing returns the focus to the line. Which one opens is chosen at the tap, from the window as it is then.
- **Accept and Reject stay whole.** A native file's proposal is never accepted with changes.

## Options considered

### Option A: `NativeProposal` in the thread, the levels in the files add-on (chosen)

| Dimension | Assessment |
|---|---|
| Size | The thread's chunk grows by the choice; the files add-on by the levels |
| Consistency | One card for a native file's proposal wherever it is shown |

**Pros:** The thread, the proposals page and the file's page show the same card.
**Cons:** The card waits on the add-on the first time it is drawn, and says "Loading the proposal…" meanwhile.

### Option B: Reuse the tool calls' sheet

**Cons:** It is built around a call's parts, which are tool ids, arguments and results. Generalising it would move bytes into the first load for a part that only native files need. The kit's dialog is already a sheet on a phone.

## Trade-off analysis

Option A keeps everything new in the files add-on. The first load pays only for choosing the card. Option B would share a component, but at the first load's cost.

## Consequences

- A thread's native file proposals read their commands' words as soon as they are drawn: one small GET each, which the client keeps for the page's life.
- Escape in the sheet goes back from a change to the list, and closes it from the list, as the tool calls' sheet does.
- Opening before and after by default, the affected pages, and the can't-preview wording and its retry come in the card's next change.

## Action items

1. [x] The thread's choice, `NativeChanges`, and their tests, on a desktop and on a phone, in light and dark.
