# ADR-0054: Readable revisions: per kind, in parts, one preview running

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland

## Context

An artifact's page lists its revisions ([ADR-0017](0017-the-artifacts-and-proposals-areas.md)), each with what changed, read from its renderer's `text`. For a kind shown as JSON that text is `JSON.stringify` of its data, so a mini app's revision ([ADR-0051](0051-mini-apps-the-sandboxed-frame-and-its-bridge.md)) was one wall of escaped text: its whole HTML a single string of `\n` and `\"`, and every revision of twelve the same. A revision said nothing of who made it or when, and artifactr's revisions held no time.

## Decision

- **A revision is dated.** artifactr's `Revision` has `at`, when it was committed: the `ts` of the events committed with it, which the storage stamps as it saves them (`dated`, beside `seal`), in memory and in SQL alike. It is stored in the revision's JSON, so no migration; a revision saved before has none, and the page leaves it out.
- **A renderer reads a revision in parts.** `Renderer.parts` gives a kind's data as named parts, each with how finely it changes (`words` or `lines`) and, where it is a source, its language. An app's are its title and its summary, by word, its HTML, by line, as `html`, and its state, as `json`; a note's is its Markdown; any other kind's is its JSON, pretty-printed, by line; a native file's is its outline, as text, named "contents". `Renderer.about` is a line beside a revision's title (an app's summary), `Renderer.preview` what its preview shows when it isn't what `render` shows, and `Renderer.runs` says its preview runs what it holds.
- **`ui`'s `Revisions` shows them,** newest first, each a native `<details>`: its summary says the version, "Latest", who made it, as the page names them, when, as how long ago with the moment on hover, and what changed in a line ("Changed the title and the HTML (+3 −1)"). The latest is open; the rest are closed, and draw nothing until opened. Open, a revision has tabs, Base UI's: **Preview**, through the kind's renderer, read-only; **Source**, each source part numbered, highlighted through the grammars `ui` already loads on demand ([ADR-0044](0044-highlighting-and-math-on-demand.md)), wrapped on asking, with Copy, and folded past 40 lines; and **Changes**, against the version before, each changed part under its name, a source's line by line with `+` and `−`, edged and marked as `<ins>` and `<del>` for a reader, its unchanged runs folded past three lines of context, and a title's or text's word by word through `Diff`. A first version has no Changes, and opens on its Source, where it has one: its content is already shown above the list.
- **One preview runs at a time.** An app's Preview runs only when asked ("Run version 3"), under the same `AppFrame` and bridge as its page and its thread, with the host's label and without its title and summary twice; running another stops the first. A preview's host keeps its state in the frame and submits nothing, so an old version changes nothing. Where apps don't run (mini apps off, no apps' origin), an app's revision has no Preview.
- **Any JSON is read as a tree.** `json`'s `render` is `JsonView`: each key beside its value, a long string or one with line breaks as a block of its own text, nested objects and lists folded past the second level, in a region of bounded height that scrolls, with Copy. Every kind that falls back to JSON, and every renderer's "can't be shown here", reads so.
- **No new dependency.** Line diffs are `client`'s jsdiff, with its bounds; the tabs are Base UI's, already a dependency; the line numbers are `ui`'s own.

## Options considered

| Option | For | Against |
|---|---|---|
| **Parts on the renderer (chosen)** | Each kind says what is worth comparing; a new kind gets JSON's at once | A renderer has more to say |
| A diff of the whole JSON, unescaped | Nothing per kind | An HTML change still reads as one line of JSON |
| **Native disclosure (chosen)** | Keyboard, names and forced colours from the browser | Its marker is styled away and drawn again |
| Every preview live | Nothing to ask for | Twelve revisions, twelve apps running at once |
| **A dated revision in artifactr (chosen)** | One read gives the time; every client has it | A field more on the protocol |
| The time read from the log | No server change | The log may be read from its head, not its start |

## Consequences

- Easier: a mini app's history reads as its changes, and its source as code.
- Easier: an application's own kind gets a readable revision by giving `parts`.
- Harder: the page compares every part of every revision as it reads them, within jsdiff's bounds; a revision past them says "too large to compare".
- Harder: revisions saved before this have no time to show.
