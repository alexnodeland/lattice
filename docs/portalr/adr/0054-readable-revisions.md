# ADR-0054: Readable revisions: per kind, in parts, one preview running

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland

## Context

An artifact's page lists its revisions ([ADR-0017](0017-the-artifacts-and-proposals-areas.md)), each with what changed, read from its renderer's `text`. For a kind shown as JSON that text is `JSON.stringify` of its data, so a mini app's revision ([ADR-0051](0051-mini-apps-the-sandboxed-frame-and-its-bridge.md)) was one wall of escaped text: its whole HTML a single string of `\n` and `\"`, and every revision of twelve the same. A revision said nothing of who made it or when, and artifactr's revisions held no time.

## Decision

- **A revision is dated.** artifactr's `Revision` has `at`, when it was committed: the `ts` of the events committed with it, which the storage stamps as it saves them (`dated`, beside `seal`), in memory and in SQL alike. It is stored in the revision's JSON, so no migration; a revision saved before has none, and the page leaves it out.
- **A renderer reads a revision in parts.** `Renderer.parts` gives a kind's data as named parts, each with how finely it changes (`words` or `lines`) and, where it is a source, its language. An app's are its title and its summary, by word, its HTML, by line, as `html`, and its state, as `json`; a note's is its Markdown; any other kind's is its JSON, pretty-printed, by line; a native file's is its outline, as text, named "contents". `Renderer.about` is a line beside a revision's title (an app's summary), `Renderer.preview` what its preview shows when it isn't what `render` shows, and `Renderer.runs` says its preview runs what it holds.
- **`ui`'s `Revisions` shows them,** newest first, each a native `<details>`: its summary says the version, "Latest", who made it (named as `author` names a message's poster: "You", a name, a person's short id, "Assistant"; the thread's email lookup isn't made here), when, as how long ago ("just now" for a clock ahead of the page's) with the moment read by a screen reader and on hover, and what changed in a line ("Changed the title and the HTML (+3 −1)"). The latest is open as the page is first drawn; a version that arrives later leaves open what the reader left open. The rest are closed and draw nothing until opened: closed, a revision names the parts that changed, by their text alone; opened, it compares them, once per pair of versions, kept by their data's identity, so a revision read again is not compared again. A part the version before had and this one hasn't is removed, and each version is read through its own kind's renderer. Open, a revision has tabs, Base UI's: **Preview**, through the kind's renderer, read-only; **Source**, each source part numbered, highlighted through the grammars `ui` already loads on demand ([ADR-0044](0044-highlighting-and-math-on-demand.md)), wrapped on asking, with Copy, and folded past 40 lines; and **Changes**, against the version before, each changed part under its name, a source's line by line with `+` and `−`, edged and marked as `<ins>` and `<del>` for a reader, its unchanged runs folded past three lines of context, and a title's or text's word by word through `Diff`. A first version has no Changes, and opens on its Source, where it has one: its content is already shown above the list.
- **One preview runs at a time, and only when asked.** An app's Preview runs only when asked ("Run version 3"), under the same `AppFrame` and bridge as its page and its thread, with the host's label and without its title and summary twice; running another stops the first. A preview writes no state, and the bridge refuses a submission at once, before the person is asked (`AppFrame`'s `preview`), so an old version changes nothing. Closing a revision or choosing another tab stops its preview; opened again, it waits to be asked. Where apps don't run (mini apps off, no apps' origin) or the artifact is archived, an app's revision has no Preview, as its page runs nothing.
- **Any JSON is read as a tree.** `json`'s `render` is `JsonView`: each key beside its value, a long string or one with line breaks as a block of its own text, nested objects and lists folded past the second level, in a region of bounded height that scrolls, with Copy; a level shows its first 100 keys or items and counts the rest. Every kind that falls back to JSON, and every renderer's "can't be shown here", reads so.
- **A comparison is bounded by size, never time.** jsdiff stops at an edit of 2,000 words or lines, and `client` compares no text longer than 200,000 characters; the 200-millisecond timeout ADR-0017 had is gone, so "too large to compare" is the same on every machine. A line diff draws its first 400 lines, and 400 more on asking; a fold's first line takes the focus of the button that showed it.
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
- Harder: a revision past the bounds says "too large to compare", however quick its comparison would have been.
- Size: the Base UI tabs land in the artifact page's lazy chunk; `JsonView` is in the shared graph, as `json` is. After this, the app's initial load is 191,310 of 200,000 bytes gzipped, its total 488,617 of 520,000.
- Not pinned by a screenshot: an app's preview running, whose frame draws from another origin.
- Harder: revisions saved before this have no time to show; the summary leaves it out.
