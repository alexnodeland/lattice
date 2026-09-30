# ADR-0004: Optimistic concurrency and append-only revisions

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Several actors edit the same artifacts concurrently: people, several chats, external agents. A version number that is incremented but never checked gives last-write-wins behaviour, where later writes silently discard earlier ones. Reconstructing an artifact's history after the fact from other records (proposals, events) is lossy, and it breaks as soon as a change bypasses those records.

## Decision

- Every edit command names the `base_version` it was computed against. If the artifact has moved on, core raises `VersionConflict(base, head, changes_since)`.
- Every accepted change writes an immutable **revision**: version, patch, resulting data, actor, and the proposal it came from, if any.
- Versions only increase. Reverting writes a new revision that restores earlier data.
- Proposals record their base version. Accepting one rebases its patch onto the current version, or raises a conflict if it no longer applies.

## Options considered

### Option A: Optimistic concurrency with append-only revisions (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Data safety | High: no silent overwrites |
| History and attribution | Complete |

**Pros:** history, attribution and undo come built in; no locks held across model calls.
**Cons:** clients must handle conflicts; revision storage grows.

### Option B: Last-write-wins

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Data safety | Poor |
| History and attribution | None |

**Pros:** simplest.
**Cons:** silent data loss under concurrency.

### Option C: Pessimistic locks

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Data safety | High |
| History and attribution | Separate concern |

**Pros:** no conflicts to handle.
**Cons:** an agent could hold a lock across seconds of model latency; locks leak on crashes.

### Option D: CRDTs

| Dimension | Assessment |
|---|---|
| Complexity | High |
| Data safety | High, with automatic merges |
| History and attribution | Available, but at operation granularity |

**Pros:** true simultaneous editing.
**Cons:** heavy dependency; schema validation after merges is awkward; agent tools would need to emit CRDT operations.

## Trade-off analysis

Collaboration here is turn-based: an agent edits between model calls, and a person edits between reads. Optimistic concurrency fits that rhythm. Conflicts are rare and informative ("someone changed this while you were working"), and the rejection carries exactly what changed, which the agent can use directly. CRDTs solve a harder problem than this one and remain possible later as a separate artifact kind.

## Consequences

- Easier: every artifact has a full, attributed history; undo is a new revision.
- Easier: conflicts become information for the agent instead of silent loss.
- Harder: UIs need a conflict path (refresh and reapply, or ask the person).
- Revisit revision storage (periodic snapshots, or compaction of old patches) if it grows large.

## Action items

1. [ ] Implement version checks and `VersionConflict` in `core.commit`.
2. [ ] Implement proposal rebasing in `core.respond`.
3. [ ] Add conformance fixtures for conflicts, rebases and reverts.
