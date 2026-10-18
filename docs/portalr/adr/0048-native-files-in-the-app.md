# ADR-0048: Native files in the app: the manifest, who has the file, its pages, a download, and its words compared

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

## Context

[lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md#portalr) keeps a Word document as a native file: an artifact whose data is a manifest naming the file's bytes, by their digest, with what the app read from them, its outline, pages, text and review. Its phase 4 asks portalr for "a renderer for native kinds in `ui`: page previews, the name, size and outline, a download, and the lease's holder and expiry", and "a revision diff [that] shows the changed text, from the text blob". artifactr's `files_router` serves a file's status, its versions' bytes, words and pages, and a proposal's ([native files ADR-0007](../../artifactr/files/adr/0007-check-out-over-http-and-the-editor-on-its-own-origin.md), [ADR-0008](../../artifactr/files/adr/0008-what-portalr-reads-of-a-native-file.md)).

Three things shape how the app reads them:

- **Every route needs the session.** The routes resolve the caller from the `Authorization` and `X-Tenant` headers, so neither an `<img src>` nor an `<a href>` can name them.
- **The app's policy allows images from itself and `data:` alone,** with no `blob:` ([ADR-0041](0041-first-party-webassembly-in-the-apps-policy.md)), and it isn't loosened for this.
- **A lease has no event.** Who has a file changes without anything on the workspace's stream.

## Decision

- **The renderer is `ui`'s `nativeFile()`,** registered for `word_document` in the app's `RENDERERS`, beside `NATIVE`, which names each native kind's app, as people call it ("WordCraft"), and the integration that switches it, `files:wordcraft`. It shows what the manifest holds and nothing it must read: the file's name, its type in words ("Word document"), its size in powers of a thousand ("48 kB"), its pages, and its outline as a list, named "Outline" but not a heading, since a renderer doesn't know how deep in a page it is drawn. Its `text` is the outline, compared line by line, as the RFC has it, and its title is the file's name. A manifest of any shape is shown as far as it goes.
- **`client` gains a fifth REST client, `files`,** typed from artifactr's committed `artifactr-files.openapi.json`, on artifactr's surface: an application mounts `files_router` beside artifactr's router, with no surface of its own in `config.json`.
- **The file's own section, on its artifact's page,** under "The file":
  - **Who has it,** from `queries.files.status`, as `ui`'s `FileHolder`, a shape and words, announced as it changes: available, a filled circle; checked out by the reader, the diamond of what waits for them; by someone else, by email where the server names people, a dotted ring, with until when; an agent's edit, the working spinner. A lease has no event, so the status is read again every 30 seconds, and every 2 while an agent's edit, which lasts seconds, holds the file, and not again once refused; its key is under the artifact's, so a change to the file reads it again at once. A status that can't be read is said under the section's heading.
  - **Its pages, a few at a time:** four, then four more each time "Show more pages" is pressed, so a long document doesn't ask the server for a render of every page at once. Each is read as bytes and shown as a `data:` URL, typed as a PNG whatever the response says, in a box of a page's proportions, named "Page n of m", with a placeholder while it is read, and a sentence where it couldn't be.
  - **A download,** read as a `Blob` through `queries.files.content` (never kept: a file is megabytes, saved once) and saved from an object URL through a link's `download`, under the file's name. A download is a navigation, which no fetch directive governs, so the policy gains no `blob:`.
  - **Where its app is off in the workspace,** by `useEnabled`'s read of grantr's flags ([ADR-0045](0045-integrations-in-admin-and-the-apps-read-of-them.md)) or by the server's own `enabled`, either: a note says it is read and downloaded here, but not checked out or edited by the agent, and who has it isn't shown. Both are read, since grantr's flags fall back to their defaults when they can't be read, and the server's is what it enforces.
  - **Where `files_router` isn't served** (the status is 404), there is no section: the manifest is all there is.
- **A revision's words are compared on demand.** A revision whose manifest names other text than the one before it, both named, offers "Changes to its words"; opened, it reads both versions' text through `queries.files.text` and shows `Diff` of them, word by word. Unopened, nothing is read. The two compared are the revision and the one before it in the list, whatever their numbers, and they are compared once for each pair, not on every event the page's stream brings. A version's words and pages never change, so their keys are `["files", tenant, workspace, ...]`, outside the artifact's, and never stale: a change to the file reads none of them again.
- **The kit's `waiting` badge keeps its diamond under forced colours,** in the system's text colour, where the accent's fill, which it was drawn on, is gone.
- **Tests:** `ui`'s unit tests and axe, and `native-file.screenshot.test.tsx` wide, narrow, colour-blind and under forced colours, in each scheme, against Linux baselines made in CI ([ADR-0019](0019-the-kits-look.md)); the app's route tests over a stubbed server; and a scenario, `native-files.feature`, in which the test application's agent drafts a document, and its page shows the outline, a page drawn under the app's policy, and the download.
- **The test application** mounts `files_router` beside artifactr's, over native files in memory read by a stand-in for WordCraft, artifactr's `FakeApp` switched by `files:wordcraft`: it reads every file in its own process, as artifactr's `Subprocess` does, for trusted files only.

## Options considered

| Option | For | Against |
|---|---|---|
| **Pages as `data:` URLs (chosen)** | The policy is unchanged | A third more bytes than the image, in memory |
| Pages as `blob:` URLs | Smaller in memory | `img-src blob:` in both UIs' policy, for this alone |
| A cookie, so `<img src>` can name the route | No fetch | A credential the browser sends to the portal's origin unasked; the UIs keep their session in `localStorage` (lattice RFC-0002) |
| **A few pages, more on request (chosen)** | A long document asks for four renders, not all | A reader presses for more |
| **Words compared on demand (chosen)** | Nothing read until asked | A press to see them |
| Every revision's words compared as the page opens | No press | Two reads a revision, and a comparison of up to 200 ms each, as the page opens |
| **Off by either grantr or the server (chosen)** | Neither can show controls the other refuses | A blip in grantr that reads the default can't turn it on where the server has it off, which is right |

## Consequences

- Easier: a Word document reads as one, its pages as its app draws them, and its words' changes are a press away.
- Harder: each page is a render on the server, kept by the browser for the session, and not shared between people.
- Deferred: the pages whose renders differ between two versions, side by side, which the RFC asks for, waits for the proposals' view, where a stale check-in's pages are shown beside the head's; check-out and check-in; and a native file's proposals, which `ProposalCard` shows as any edit's until then.

## Action items

1. [x] `nativeFile()`, `FileHolder` and `PageStrip` in `ui`, with their tests and screenshots.
2. [x] `client`'s `files` client and queries; the app's file section and its words compared; the test application's native files, and the scenario.
3. [x] Check-out and check-in ([ADR-0049](0049-checking-a-native-file-out-and-in.md)).
4. [x] A native file's proposals, with both versions' pages, and the RFC's scenarios ([ADR-0050](0050-a-native-files-proposals-and-the-pilots-scenarios.md)).
