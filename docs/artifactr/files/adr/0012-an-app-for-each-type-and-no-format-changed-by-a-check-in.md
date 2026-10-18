# ADR-0012: An app for each native type, and no format changed by a check-in

**Status:** Accepted
**Date:** 2026-10-18
**Deciders:** Alex Nodeland
**Amends:** [ADR-0006](0006-the-agents-tools-behind-each-apps-switch.md), whose `key_of` claimed every native file for one app, and [ADR-0007](0007-check-out-over-http-and-the-editor-on-its-own-origin.md), whose check-in took any bytes as the format checked out

## Context

`NativeFiles` took one app, and [ADR-0006](0006-the-agents-tools-behind-each-apps-switch.md) said its `key_of` assumed one app a deployment, "until a second app's adapter says which formats are its". Twelve apps are coming ([ADR-0009](0009-each-crafting-app-declared-once-on-one-of-two-dialects.md)), each behind its own switch.

A check-in put the uploaded bytes under the head's media type, whatever they were. But an editor can save another format than it opened: GridCraft's browser build saves a workbook opened from `.csv` as `.xlsx` ([ADR-0010](0010-a-shim-beside-the-build-and-talk-level-one-plus.md)'s pilot), DesignCraft reads INDD and writes IDML, CADCraft's browser build writes DXF only, and WordCraft opens `.odt` and `.docm` as well as `.docx`. A check-in of such a file would have become a revision claiming the old format, converted without anyone saying so.

## Decision

- **`NativeFiles` takes an app for each native type,** `NativeFiles(blobs, checkouts, {WordDocument: wordcraft, Workbook: gridcraft})`, or one app for every type, as before. A type's app is its own, or else its nearest base's. `app_of(type)` names it, and replaces the `app` property; an upload of a type no app reads is `ValidationFailed`.
- **Each file is switched by its own app's key.** Every write reads the file first, to know its app, then asks that app's switch, still before any lease is taken, so a missing file is `NotFound` before an app that is off is `NotEnabled`, and a check-out, an edit and a render read the head once more than they did. Every write asks the switch of its file's app, and refuses with `NotEnabled` while it is off; `enabled(ws, type)` asks for one type, and `enabled(ws)` whether any app is on, which is when the agent's tools are offered. `key_of` gives a native kind its app's key, and none to a type no app reads. `find_commands` takes the file whose app to ask, `find_commands(artifact_id, query)`.
- **A check-in never changes a file's format.** It is refused, as `FormatChanged`, an `InvalidState` (409) naming the format checked out and the one checked in, when the file says it is another format, by the check-in's `Content-Type` (`check_in(..., media_type=)`), or when the app reads it as another, by the inspection's new `media_type`. The router reads no format from a `Content-Type` a client sends by default (`application/octet-stream`, a form's, `text/plain`). The head keeps its format, and the person uploads the file as a new one. An upload whose app reads it as another format than it was declared is `ValidationFailed`.
- **An app says what it reads a file as** in `Inspection.media_type`. The port allows None, for the fake; a crafting app's adapter must name one, or its call is `crashed`, so no adapter lets a check-in through unread. WordCraft's reads a Word package's main part, `.docx`, `.docm`, `.dotx` or `.dotm`, and an OpenDocument's `mimetype`, so an `.odt` or a `.docm` checked in over a `.docx` is refused.
- **A format change is never a proposal.** A native type holds the formats it lists, so most changes couldn't be one; and a proposal that changed a file's format would ask its reviewer to accept a conversion they can't see. Moving a file to another format is a new artifact, which keeps the old one's history intact.
- **The fidelity matrix states each format's limits.** Each app's corpus is of the format it keeps, and a feature its release doesn't keep is listed as not supported; a format an app only reads, such as DesignCraft's INDD, or writes only lossily, such as VectorCraft's AI, is in no corpus it would pass, and its adapter's documents say so.

## Options considered

### Option A: An app for each type, and refusal (chosen)

| Dimension | Assessment |
|---|---|
| Fit | Each file is read, edited and switched by its own app |
| Safety | No revision ever names bytes of another format than its manifest says |
| Cost | The person uploads a converted file as a new one |

### Option B: A format change as a proposal, with a notice

**Cons:** the manifest's type may not hold the new format, and the reviewer approves a conversion from two renders, not from the file.

### Option C: Trust the declared type alone

**Cons:** a browser's download names a file by its extension, and the app is the only reader that can tell.

## Trade-off analysis

Refusing costs the person a second upload when they meant to convert; accepting would let a revision hold one format under another's name, which every later reader, the app and the agent included, would misread.

## Consequences

- Easier: each app's work adds its type and its adapter to the mapping, and its key governs only its files.
- Easier: portalr can check in each save the shim hands over, and show a refusal that says which format came back.
- Harder: each crafting app's adapter reads its format from the file, as WordCraft's reads a package's main part.
- Revisit: converting on purpose, as a new artifact made from an old one, if people ask for it.

## Action items

1. [x] `NativeFiles` with an app for each type; `app_of`; `enabled(ws, type)`; `key_of` by type; `find_commands(artifact_id, query)`.
2. [x] `FormatChanged`, `Inspection.media_type`, `check_in(..., media_type=)`, the router's `Content-Type`; WordCraft's `media_type`.
3. [x] `Headless` refuses an inspection that names no format.
