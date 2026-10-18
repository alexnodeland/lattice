# ADR-0008: What portalr reads of a native file: its words, its own check-out, its limit, and a proposal

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland
**Amends:** [ADR-0007](0007-check-out-over-http-and-the-editor-on-its-own-origin.md), whose routes these join

## Context

[ADR-0007](0007-check-out-over-http-and-the-editor-on-its-own-origin.md) gave `files_router` a file's status, check-out, extension, check-in, and a version's bytes and pages. portalr's screens for phase 4 of [lattice RFC-0003](../../../rfcs/0003-native-files-as-artifacts.md#portalr) need four things those routes don't give:

- **A revision's words.** "A revision diff shows the changed text, from the text blob." The manifest names the text blob by its digest, and no route serves it.
- **The reader's own check-out.** A check-in and an extension name the check-out, but the status names only whose it is. A person who checked a file out in one tab, or before a reload, has no way back to its id.
- **The limit.** The router refuses a check-in past `limit`, but the page can't say so before the upload starts.
- **A proposal's file.** A stale check-in is kept as a proposal, and "the reviewer sees both versions' pages". A proposal's content is named only in its patch, and the routes read versions alone.

## Decision

- **`GET /workspaces/{w}/files/{a}/versions/{v}/text`:** a version's words, as plain text, as `NativeFiles.read(part="text")` reads them, with the headers a version's bytes have: `nosniff`, `Content-Security-Policy: sandbox`, `private, no-store`, but no attachment. A version with no text is `ContentUnavailable`, 409, as unavailable content is everywhere.
- **`Lease.checkout_id`:** the check-out's id, given only to the person whose check-out it is, read from the lease's holder, `checkout:<id>:<participant>`, when its participant is the caller's. Anyone else, and an agent's edit, gets None: the id is the only handle on a check-in, and `NativeFiles` refuses it from anyone else regardless.
- **`FileStatus.limit`:** the router's own `limit`, in bytes, the largest check-in it takes.
- **`NativeFiles.proposed(ws, proposal_id, part=)` and `render_proposed(ws, proposal_id, page)`,** and two routes over them, `GET /workspaces/{w}/proposals/{p}/text` and `GET /workspaces/{w}/proposals/{p}/pages/{n}`. The proposal is read through the workspace (`Workspace.proposal`, which hides what the actor may not read), then its file (`Workspace.get(NativeFile, ...)`), so a hidden one of either is a missing one, 404. The blob is the one the proposal's JSON Patch last replaces the part with, as JSON Patch applies its operations in order, and as `revise` builds every native revision; a proposal that replaces none, or clears it, such as an archive or a hand-written patch, is `ContentUnavailable`, 409. The bytes are read under the proposal's artifact's key, so a proposal can name no other artifact's bytes. Each route still names a workspace and a proposal, never a bare digest.
- The OpenAPI document, `schemas/artifactr-files.openapi.json`, is regenerated, and portalr's client is typed from it.

## Options considered

### Option A: Reads beside the routes there are, each through the workspace (chosen)

| Dimension | Assessment |
|---|---|
| Fit | Each answers one need of the screens, through the same access checks as every other route |
| Size | Two methods on `NativeFiles`, three routes, two fields |
| Risk | A proposal's bytes are read only as its artifact's |

### Option B: A route for a blob by its digest

**Cons:** RFC-0003 rules it out: every route names an artifact and a revision, so that a digest learned elsewhere opens nothing.

### Option C: Keep the check-out's id in the browser

**Cons:** lost with the tab, or on another device; the server already knows whose the check-out is.

## Trade-off analysis

The four reads are small, and each is resolved as the routes before them are. The alternative for each either breaks the RFC's rule on digests or leaves the screens unable to do what the RFC asks of them.

## Consequences

- Easier: portalr compares a revision's words, takes a person back to their check-out, refuses a file too large before sending it, and shows a stale check-in's pages beside the head's.
- Harder: a proposal's pages are rendered on demand, a render each, as a version's are.
- Revisit: a cache for renders, keyed as RFC-0003 has it, once a deployment renders often.

## Action items

1. [x] The text route, the check-out's id and the limit, and the proposal's reads, with their tests and the regenerated document.
2. [ ] portalr's screens that read them (lattice RFC-0003, phase 4).
