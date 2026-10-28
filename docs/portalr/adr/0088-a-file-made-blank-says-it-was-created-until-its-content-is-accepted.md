# ADR-0088: A file made blank says it was created, until its content is accepted

**Status:** Accepted
**Date:** 2026-10-28
**Deciders:** Alex Nodeland
**Amends:** [ADR-0055](0055-every-kind-inline-and-a-native-file-read-and-edited-in-its-thread.md) (a native file read inline in its thread)

## Context

An agent makes a native file in two steps. First it creates the file blank, as the file's app makes one, which is applied as the person it acts for; the file's provenance says `blank`. Then it writes the file's content as an edit, which the type's `propose` write policy keeps as a proposal for a person to accept.

The thread draws every artifact made in it where it was made ([ADR-0055](0055-every-kind-inline-and-a-native-file-read-and-edited-in-its-thread.md)). So, until the proposal is accepted, the thread shows a blank Word document, with its page, its download and its full view, under the agent's turn, and the proposal further down. The owner found that misleading: it reads as what the agent made, and the agent made nothing blank on purpose.

The owner decided (2026-10-28): while its content waits, the card should only say the file was created; once the proposal is accepted, the card should draw the file.

## Decision

- **A native file whose latest version is blank (`provenance.source` is `blank`), with an open proposal to change it, is drawn as a card that says it was created**: its type and name, "Created. Its content waits in a proposal in this thread: accept it to see the file here.", and the link to its own page. It has no page, no download, no editor and no full view.
- **Once no proposal waits on it, the card draws the file as before.** Accepting the proposal makes a new version that isn't blank, so the card reads it as any file. A file left blank, its proposal rejected, is drawn as it is: blank is then what it really is.
- **A file with content is drawn as it is** while a proposal waits on it: what it holds now is true, and the proposal says what would change.
- The thread counts the open proposals on each artifact it draws, in the column and in the pane beside it ([ADR-0087](0087-a-command-first-layout-a-top-bar-a-palette-a-table-and-a-split-view.md)).

## Options considered

| Option | For | Against |
|---|---|---|
| **A created card while blank and proposed on (chosen)** | Says what is true; nothing new to fetch | The file's content is seen only on the proposal, or its page, until accepted |
| Draw the proposal's content in the card | The card shows what the agent wrote | Shows unaccepted content as if it were the file; the proposal's preview already does this, on demand |
| Hide the card until accepted | Nothing misleading | The thread loses the record that a file was made, and the link to it |
| Have the agent create the file with its content in one proposal | One step | Changes artifactr's write policy for native files; a blank file is how its app makes one |

## Trade-off analysis

The card's job is to show what exists. A blank file with content waiting is a file that exists but isn't yet what anyone meant, so the honest card names it and points to the proposal. Drawing the proposal's content would blur what is accepted with what isn't, which proposals exist to keep apart.

## Consequences

- Easier: a person reading the thread sees that the file exists and that its content waits for them, not a blank page.
- Harder: nothing new is fetched, but the card now depends on the thread's proposals as well as the file's revisions.
- To revisit: drawing a preview of the proposal's first page in the card, if people want to see it before they open the proposal.

## Action items

1. [x] The created card in `ThreadArtifact`, and the count of open proposals in the thread page, with tests in `thread-inline.test.tsx`.
