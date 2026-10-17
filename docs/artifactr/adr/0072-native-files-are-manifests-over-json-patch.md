# ADR-0072: Native files are manifests over JSON Patch

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Records [lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md)'s D1. Keeps [ADR-0003](0003-artifact-types-as-pydantic-subclasses.md)'s two patch kinds.

## Context

A file in a native format, such as a `.docx`, is often megabytes, and only its own application reads and writes it faithfully. Every revision stores its resulting data ([ADR-0004](0004-optimistic-concurrency-and-revisions.md)), events carry it, WebSocket replays send it, and relayr bridges it into reflexr, so the bytes can't be an artifact's data. And an agent edits the file by a batch of the application's commands, whose result exists only after the application has run, for seconds, outside the transaction that holds the workspace's lock ([ADR-0021](0021-sql-storage.md)).

## Decision

- **A native file's artifact is a manifest.** Its data names the file's bytes by their SHA-256 in a blob store, with their size and media type, and holds a fingerprint (the digest of the content with what each save stamps left out), the text and the review (comments and tracked changes) as blobs of their own, an outline and how the content was made (its provenance). The bytes live in the blob store of the `artifactr-files-ai` package, which defines the types; artifactr defines none of it.
- **A revision is ordinary JSON Patch.** It first tests `/content/sha256` against the digest it was made from, then replaces `/content`, `/provenance`, `/fingerprint`, `/text`, `/review`, `/outline` and `/pages`. No third patch kind is added: core is pure ([ADR-0001](0001-python-library-with-sans-io-core.md)) and couldn't run the application to apply a batch.
- **The `test` guards acceptance.** A stale direct edit fails first on `base_version`, as `VersionConflict`. A proposal is re-applied to the head when it is accepted, and acceptance checks no version, so without the test a proposal made against an old version would replace everything since. With it, accepting a stale proposal fails with `PatchFailed`.
- **A stale proposal is outdated, never rebased.** Its author makes a new one, with `base_version` at the head and a test on the head's digest.
- **The summary comes from the batch or the check-in.** The package passes `summary=`, so a change note doesn't read as the patch's operations.

## Options considered

### Option A: A manifest, edited by JSON Patch with a test on the digest (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low in artifactr: nothing changes |
| Log | A kilobyte or so a revision, plus the outline |
| Staleness | `base_version` for a direct edit, the `test` for an accepted proposal |

**Pros:** every surface, the log, proposals and feedback work as for any type.
**Cons:** two stores to keep consistent; the package puts bytes first and collects what no revision names.

### Option B: A third patch kind, a command batch

**Cons:** core can't apply it: its result exists only after the application has run, outside the transaction.

### Option C: The bytes in the artifact's data

**Cons:** every revision, event, replay and bridged event would carry megabytes.

## Trade-off analysis

Option A changes nothing in artifactr and keeps the log small; what it costs, keeping the blob store and the log consistent, is the package's to pay, by putting first and collecting later. Option B can't be built on a pure core, and option C makes every reader of the log pay for every file.

## Consequences

- Easier: a native file is reviewed, proposed, attributed and evaluated as any artifact is.
- Harder: accepting a stale proposal fails rather than merging, which is the point: the reviewer sees it as outdated.
- Harder: `edit_artifact` over REST or MCP can write a manifest naming a digest that isn't stored. The package then shows the content as unavailable, and refuses to edit it until it is replaced.

## Action items

1. [x] The types, the patch with its test, and the blob store, in `artifactr-files-ai`'s phase 1.

## Note (2026-10-17): the package is artifactr's `files` extra

`artifactr-files-ai`, named above, was never released: before its first release it became artifactr's `files` extra, `artifactr-ai[files]`, imported as `artifactr.files` ([lattice ADR-0026](../../adr/0026-a-distribution-needs-a-reason-integrations-are-extras.md)). The decision above is unchanged; the rest of artifactr still imports nothing of it.
