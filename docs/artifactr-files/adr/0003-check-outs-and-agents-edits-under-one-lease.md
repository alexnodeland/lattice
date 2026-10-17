# ADR-0003: Check-outs and agents' edits under one lease

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Records [lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md)'s D3, on the package's side; the lease itself is [artifactr ADR-0071](../../artifactr/adr/0071-a-lease-on-an-artifact.md).

## Context

A native file can't be merged: two writers at once lose one's work. `lock` is the pilot's only merge strategy, one writer at a time, through artifactr's lease on the artifact. A person edits for hours in an app the server can't see into, and an agent for seconds through the app run headless.

## Decision

- **A check-out is a record in the package,** `Checkout`, kept in `artifactr_files_checkouts`: its id, the artifact, the version and digest checked out, the actor and the expiry. Its lease's holder is `checkout:<id>:<participant>`, which names the record, so two tabs are two holders and a refusal says who has the file.
- **A check-out lasts eight hours by default,** and is extended by acquiring the lease again. Nothing renews it in the background, because the browser build can't tell the portal it is still open. Only its actor checks it in or extends it; anyone else is refused with `Forbidden`.
- **A check-in's base is the record's,** never the upload's, for its test and its provenance. It takes its lease again first, which renews one that lapsed if no one took it, then commits directly, since write policies bind agents only. A file whose fingerprint is the head's commits nothing. A stale check-in, whose lease lapsed while someone else took the file or committed, is kept as a proposal against the head: `base_version` at the head, a test on the head's digest, and the record's digest as its provenance's base. It is the one proposal from a person, and someone else's check-out is never overwritten by it.
- **A check-in ends the check-out.** Its record is closed and its lease released. A closed check-out isn't extended, and is checked in again only with the same file, which does nothing, so a retried check-in succeeds.
- **An agent's edit takes a lease of its own,** `edit:<uuid>`, unique per call, for the app's call and the commit: 45 seconds by default, the app's 30-second deadline and the commit, never renewed. It is released however the call ends. An edit that outlives it is still refused at commit, by its base version and the test, if anyone else committed meanwhile.
- **A busy agent plans again.** While someone else holds the lease, the edit is refused with `ArtifactBusy` and the lease, or `None` if the lease ended in between, when it may try at once. It never queues a proposal that would be stale on arrival.
- **A check-out the package fails to record releases its lease,** since its holder is new and nothing else would release it.

## Options considered

### Option A: One lease, held by check-outs for hours and edits for seconds (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: two holders' shapes over one artifactr lease |
| People | One writer, with who and until when shown to viewers |
| Agents | Refused at once while busy, and plan again after |

**Pros:** one rule for every writer; nothing is stale on arrival.
**Cons:** coarse turns: an agent waits hours for a check-out.

### Option B: Proposals queued behind a check-out

**Cons:** each would be made against the version before the check-in, so stale on arrival.

### Option C: Last write wins

**Cons:** a check-in after an agent's edit, or the other way round, would silently drop one.

## Trade-off analysis

Option A trades concurrency, which native files can't have, for never losing a write and never making work that is stale on arrival. Option B makes that work anyway, and C loses it.

## Consequences

- Easier: a busy refusal says who has the file and until when.
- Harder: an agent's work on a checked-out file waits for the check-in.
- Deviation from RFC-0003: the holder names the actor's `participant` (`user:alice`), not an "actor id": not every artifactr actor has an id, and the participant is what artifactr compares actors by.
- Revisit: closed check-out records are kept; how long is portalr's check-out's to decide, in phase 4.

## Action items

1. [x] `Checkout`, `Checkouts`, `InMemoryCheckouts` and `SqlCheckouts`; `NativeFiles.check_out`, `extend`, `check_in` and `edit`, tested for renewal, a busy agent, a stale check-in, an idempotent retry and a stale proposal rebuilt at the head.
