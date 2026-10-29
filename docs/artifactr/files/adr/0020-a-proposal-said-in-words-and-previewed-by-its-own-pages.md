# ADR-0020: A proposal said in words from its commands, and previewed by its own pages

**Status:** Accepted
**Date:** 2026-10-28
**Deciders:** Alex Nodeland

## Context

For a native file, every agent edit is a proposal: the types' write policy is `propose`, in Ask and Auto alike ([ADR-0019](0019-the-agent-creates-native-files.md)). So Accept is the only way an agent's content gets into a file, and the reviewer has to know what accepting does. A proposal's card said only its one-line summary ("Write the travel plan"). Issue 1090's owner: "I can't knowledgeably accept with no info. It should show diff etc."

A reviewer needs four things, each deeper than the last, the way a run's tool calls fold ([portalr ADR-0053](../../../portalr/adr/0053-the-chats-questions-tool-calls-sides-failures-and-streaming.md)):

1. what the batch does, in words;
2. each command, with its arguments;
3. the pages after, beside the pages before;
4. the batch, as listed.

Most of this already exists. An agent's edit runs its batch on the head's bytes in the app (`NativeFiles.edit`) before anything is committed. The proposal stores the result: its bytes, its words and its page count, all named in its JSON Patch. The batch itself is stored as canonical JSON, a blob that the proposal's `provenance.commands` names. The proposal's pages and words are already served (`GET .../proposals/{id}/pages/{n}` and `.../text`, [ADR-0008](0008-what-portalr-reads-of-a-native-file.md)), and portalr compares them with the head's on request ([portalr ADR-0050](../../../portalr/adr/0050-a-native-files-proposals-and-the-pilots-scenarios.md)). The missing pieces are levels 1, 2 and 4.

## Decision

- **`GET /workspaces/{ws}/proposals/{id}/commands`** answers `{summary, items: [{text, name, args}], total}` through `NativeFiles.proposed_commands`. It reads the batch from the blob named by the provenance that the proposal's patch gives the file. It is read the way the proposal's other reads are: the proposal and then its file are resolved through the workspace. So a hidden proposal, or one on a hidden file, is answered as missing (404), and the workspace's `authorize` decides who may read it, as for any file read. A proposal made by no commands, such as a person's check-in kept as a proposal, has none: `ContentUnavailable`, 409, which the client reads as nothing to say. A batch blob that doesn't hold a list of commands gets the same answer.
- **The words are made in Python, from the batch alone,** by `artifactr.files.native.describe(app, commands)`, keyed by the app named in the provenance. The worker is not called, so there is no deadline, no reading and no pace. One table serves every surface: the card now, and later the agent's tool result and change note. Each craft that has a table names its commands in its own verbs, read from its pinned release's `list_commands`. A command that no table names, or a counted one with no text, is counted ("and runs 2 other commands"), and listed by its name, quoting only a word-like argument (`text`, `title`, `name`, `label`), never a path or a token; a `path` argument is listed as `…`. A batch from a craft with no table is said by its command names ("Runs 3 commands: add_paragraph ×3."). The line is in the present tense, because it says what accepting does. Each item quotes at most 80 characters of its argument. Its `args` keep at most 1,000 characters of each string, and at most 200 items are listed, with `total` counting them all, so the batch as listed is not always the batch as sent. A batch over 4 MiB, or a provenance that doesn't validate, is not read: 409. The other crafts' tables follow in their own change. The two tables say, for example:

  - WordCraft 0.11: "Makes 2 headings, types 412 characters, starts 11 new paragraphs and inserts a table."
  - DeckCraft 0.7: "Adds 6 slides: Title, Itinerary, Budget, Day 1, Day 2 and 1 more."

- **The preview is the proposal's own pages:** the existing proposed-pages route, unchanged. An agent's proposal already holds the bytes that its batch made, so nothing is applied to a scratch copy to preview it, and a preview never commits or stores anything. A future proposal kind that carries only commands, with no bytes applied, would need a scratch-copy apply in the worker; that is not built here.
- **Caching is the page routes'** ([ADR-0018](0018-a-page-takes-a-reading-is-kept-and-is-paced.md)): a process-local LRU, keyed by app, bytes, page and scale, then `Cache-Control: private, max-age=86400` with an `ETag` of the PNG. The commands route is cached by the client for the page's life, since a proposal's batch never changes.
- **Images are rendered at scale 1,** as every page is. In the `commands` dialect that makes the longer side `PREVIEW`, 1024 pixels. In the `tools` dialect it is a pixel per point. There is no new size.
- **A craft that can't render a page** (its `render` is false in `CRAFTS`) says: "<App> can't show a picture of this change. Its words and its list of changes are above." A page that fails for any other normal reason, such as being busy, too slow or refused, says that in words and offers to try again. It is never called "damaged". The wording and the retry are built in the card's next change.
- **The card compares with the head, not with the proposal's `base_version`.** For every proposal that can be accepted, the two hold the same content: Accept is enabled only while the proposal's tested digest is the head's (portalr ADR-0050), so comparing with either shows the same thing. For an outdated proposal, Accept is disabled, and the card says to reject it and ask again. There the head is what the reader needs to see, because it is what any new proposal will be made against. Comparing with the head also needs no extra read of the base version's revision.

## Options considered

### Option A: Words from the batch in the API process, pages as stored (chosen)

| Dimension | Assessment |
|---|---|
| Cost | Reading one small blob; no worker call |
| Truth | The words are of the batch that made the stored bytes; the pages are those bytes |
| Scope | One route, one module of tables |

**Pros:** It is cheap, needs no deadline, and is true to what accepting commits.
**Cons:** The tables are hand-written, and a craft release that renames a command leaves it to the fallback: it is said by its name, never wrongly.

### Option B: A `describe` hook on the App port

**Cons:** In production, the application holds a `Worker`, not the adapter, so every description would be a round trip to the worker over HTTP, holding a reading. A new required member of the `App` protocol is also a public API break for every adapter and for `FakeApp`. The words need nothing from the app.

### Option C: A preview route that applies the batch to a scratch copy

**Cons:** It costs a worker call and a reading for each preview, only to make bytes that the proposal already stores.

## Trade-off analysis

Option A keeps every level read-only and cheap, and puts the wording where every surface can reach it: the `native` layer, which the agent's tools and the router both import. Option B would put the same tables behind a network hop. Option C solves a problem that agents' proposals don't have; it stays open for a command-only kind.

## Consequences

- A reviewer reads what a proposal does before opening anything, and every level is a read-only GET.
- The models are `ProposalDescription` and `CommandChange`.
- `ContentUnavailable.part` widens to `Part | Literal["commands"]`.
- The tables have to follow each craft's pinned release. When a command is renamed, it falls back to its own name.
- The other crafts' tables, the open-by-default before and after, affected pages, and the can't-preview wording are later changes (issue 1090).

> **Amended (2026-10-28) by [portalr ADR-0091](../../../portalr/adr/0091-a-native-files-proposal-opens-on-its-first-changed-page.md):** each item names the `pages` of the proposed file it changes, from 1, where its craft can say: DeckCraft's added slides, WordCraft's header and footer commands' `page`; `describe` takes the head's page count as `before`. `ContentUnavailable` says `reason: content_unavailable` and its `part`. Every craft that `stackr`'s template wires now has a table, read from its pinned catalogue (FreeCAD's and Blender's from the adapter's steps), or is in `GENERIC`, said by names on purpose. The can't-preview line reads "<App> can't show a picture of this change. Its words and commands are listed above."
