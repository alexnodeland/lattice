# ADR-0017: The Artifacts and Proposals areas: renderers by kind, and diffs by revision

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

lattice RFC-0002 gives the app an Artifacts area, each artifact with its renderer, its revisions and their diffs, and its open proposals, and a Proposals area, every open proposal in the workspace to accept or reject. `ui` renders artifacts through "a registry of renderers keyed by artifact kind, which an application extends with its own", and a kind without one as formatted JSON. The workspace's stream already holds each artifact's kind and latest version, and every proposal ([ADR-0016](0016-the-threads-area.md)); it doesn't carry an artifact's data, which artifactr's REST surface reads.

## Decision

- **`ui` renders artifacts through a registry** keyed by kind: a `Renderer` shows a kind's data, and says what text its revisions' changes are read from and how finely, by word or by line. `markdown(field)` is one, for a kind whose Markdown is in a field, through the same `Markdown` component as the chat, so no HTML ever renders; `json` is every other kind's, its data formatted. A kind named for something every object has, such as `constructor`, is still JSON.
- **The app registers the kinds it knows:** the template's `note`, as Markdown in its `text`. An application with kinds of its own adds them to `src/renderers.ts`.
- **Diffs are jsdiff's, made in `client`** (`changes(before, after, by)`), and shown by `ui`'s `Diff`, which marks what was added and removed for screen readers as well as by colour and line. jsdiff stops at an edit of 2,000 words or lines, and a revision past it is "too large to compare" (once also after 200 milliseconds; ADR-0054 bounds it by size alone). An artifact's page works its revisions' changes out once each time it reads them, in version order, not on every event the stream brings.
- **An artifact's page reads its revisions over REST,** each with its whole data, oldest first, whose last is the artifact as it is now; artifactr types that read, and not the artifact's own. It reads them again when the workspace's log moves the artifact past the latest it has, and an artifact artifactr doesn't have, or has no revision of, is not found at once: a read refused with a 4xx is never tried again. Its open proposals come from the stream.
- **The Artifacts area lists the workspace's artifacts that aren't archived,** from the stream, each by kind and latest version.
- **The Proposals area reads the stream,** like Threads: every proposal, the open ones first, each with a link to the artifact it would change.
- **Each area's feature** makes its own note, through the scripted agent, so it runs again on one application: an accepted proposal's change in the note and its latest revision; accepting on the note's page; rejecting in the Proposals area.

## Options considered

| Option | For | Against |
|---|---|---|
| **A registry by kind, JSON otherwise (chosen)** | A new kind shows at once; an application adds its own | A kind's look is code in the app |
| A renderer guessed from the data's shape | Nothing to register | A guess: a `text` field isn't always Markdown |
| **Diffs in `client`, rendered by `ui` (chosen)** | `ui` stays rendering what it is given | Two places to read |
| **Revisions over REST (chosen)** | Each has its whole data, typed | One read per artifact opened |
| Rebuilding data from the log's patches | No REST read | The stream carries no artifact's data to patch |

## Consequences

- Easier: the admin UI, and any application's own screens, render artifacts through the same registry.
- Harder: a deployment with its own kinds builds the app with its renderers, until the template carries them (phase 7).

## Amendment, 2026-10-28: a rule as its pipeline

relayr's rules from chat ([relayr ADR-0028](../../relayr/adr/0028-rules-from-chat.md)) propose a `rule` artifact, `{rule}`, which had no renderer, so a person deciding whether a rule should run on their behalf read its JSON, in its thread, its revisions, its proposals and on the Rules page.

- **`ui` has a `rule` renderer, and the app registers it.** It draws the rule as the pipeline reflexr runs, a stage each: event types, filter, pattern, dedupe, throttle, scope, action, retries, timeout, and how it runs. Its words are read from reflexr's rule schema's generated types (`ReflexrRulesV1`), not a copy of them. A part whose kind it doesn't know is that part's JSON, in its place; the rest still reads. Its JSON is folded beneath it, to copy. Data with no rule in it is JSON, as before.
- **Its revisions compare it stage by stage.** The renderer's parts are its stages, each always there (a missing throttle is "none"), so a stage added or changed reads as one change with its old and new value. A stage of several lines (filter, pattern, action) is compared by line, the others by word. A proposed edit is compared the same way: `ui`'s `ProposedChanges` shows a revision's changes for the version the edit was made on and what its JSON Patch would make, which the app applies to a copy. An edit whose base version can't be read, or whose patch doesn't apply, shows only its card, as before. A proposed rule shows as its pipeline, folded once it is decided.
- **What the preview found is said with it.** relayr ends the proposal's rationale with "It would have fired N times since …"; the artifact, in its thread and on its page, says the sentence from its newest accepted proposal. An open edit's card already says its own.
- **The Rules page uses the same view.** A rule's page, code or stored, shows its pipeline in place of the summary [ADR-0085](0085-polish-one-shape-per-part-and-what-is-folded.md) gave it, with whether it is enabled beside its description; its JSON stays folded beneath, and a stored rule's editor keeps its JSON field.
- **No add-on.** The renderer is in the route chunks that draw artifacts and rules, not the first visit's, which it doesn't grow; it adds 3,555 B gzip to the app's total, on a Mac build.
- **A rule's page, opened cold, loads the chat's chunks too.** The renderer's chunk is reached with the chat's and the artifacts' (about 280 KB gzip, against the Rules list's 96 KB). A chunk of its own for the pipeline was measured to grow the first visit by 200 to 400 B, which the budget has no room for, because every chunk's name is carried in the routes' preload maps. In practice a thread opened first has loaded them already.
