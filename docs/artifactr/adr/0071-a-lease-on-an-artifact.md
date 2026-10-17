# ADR-0071: A lease on an artifact

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Narrows [ADR-0004](0004-optimistic-concurrency-and-revisions.md)'s rejection of pessimistic locks, for the holders that need one. Records [lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md)'s D3 and D6.

## Context

[lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md) gives artifactr artifact types for files in native formats, in the `artifactr-files-ai` package. A person edits such a file in its own application, for hours, and checks it back in; an agent edits it through the same application run headless, for seconds. Two of them editing at once can't be merged: a `.docx` has no patch that commutes with another. One writer at a time is the pilot's only merge strategy, the lock.

[ADR-0004](0004-optimistic-concurrency-and-revisions.md) rejected pessimistic locks (its option C) because an agent could hold one across seconds of model latency, and locks leak on crashes. Neither holds here. An agent holds the lease across one call of the application and its commit, never across a model call, and every lease expires on its own.

The lease has to be on `Workspace`, not taken on `Storage` by the package: a lease taken straight on storage would skip `authorize` and [ADR-0062](0062-restricted-items-left-out-of-every-read.md)'s hiding of restricted artifacts. `Workspace.claim_thread` is the precedent, a lease on a thread over the same storage methods.

## Decision

- **`Workspace` gains three methods.** `lease_artifact(artifact_id, *, holder, ttl)` takes or renews the lease and returns an `ArtifactLease` (the artifact, its holder and its expiry); `artifact_lease(artifact_id)` returns it, or `None` if no one holds it now; `release_artifact(artifact_id, *, holder)` releases it if `holder` has it. Nothing renews a lease in the background.
- **Its semantics are `acquire_lease`'s.** The same holder acquiring again renews it, for `ttl` from now; another holder may take it once `expires_at <= now`, by the storage's clock. A `ttl` that isn't positive is refused with `ValidationFailed`.
- **Another holder is refused with `ArtifactBusy`,** an `InvalidState` exported beside `ThreadBusy`. Its `lease` is the lease that refused it, read after the refusal, or `None` if that lease ended in between: the caller may then try again at once. A lease taken and lost before it could be read back, as when it lapses at once and another holder takes it, is refused the same way.
- **The access checks.** `lease_artifact` and `release_artifact` ask `artifactr:edit_artifact` about the artifact; `artifact_lease` is a read, which viewers are shown, and asks `artifactr:read_artifacts`. A restricted artifact answers as a missing one does, with `NotFound`, and so does an artifact that doesn't exist. `ACTIONS` doesn't grow, so grantr's catalog is unchanged.
- **The key is `artifact:<id>`,** which can't collide with a thread claim's `thread:<id>`.
- **`Storage` gains one read, `lease(scope, key)`,** which returns the holder and expiry of a lease no one has let lapse, or `None`. Both of artifactr's storages implement it. A storage an application wrote must add it; the owner accepted that (RFC-0003's D6). `scripts/breaks.py` doesn't report a method added to a protocol, so, as D6 says, the change isn't marked breaking.
- **The lease is advisory.** Core doesn't know of it, so `edit_artifact` over REST or MCP is not refused while someone holds it. Its holders guard their own writes as anyone's are guarded, by `base_version` and, for native files, a JSON Patch `test` on the content's digest ([ADR-0072](0072-native-files-are-manifests-over-json-patch.md)), so a write past a lease fails or makes the holder's next write stale, and is never silent.
- **No release when a call is cut short.** `claim_thread` releases a lease whose acquisition failed, since its holder is new every time. A lease on an artifact is renewed by acquiring it again, and releasing on failure would end a check-out its holder still has, so `lease_artifact` leaves that to its caller, which knows whether its holder is new.

## Options considered

### Option A: A lease on `Workspace`, with one read added to `Storage` (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: three methods over the lease storage already has, and one read |
| Access | Asked and hidden as every workspace method is (ADR-0056, ADR-0062) |
| Storage protocol | `lease(scope, key)`: a storage written outside artifactr adds it |

**Pros:** one lease for every holder, checked like everything else; a refusal names who has the artifact.
**Cons:** a storage an application wrote must add a method.

### Option B: The lease's read kept outside `Storage`

The holder and expiry would be kept by the package that takes the lease, in its own table.

**Pros:** no change to storage's protocol.
**Cons:** two records of one lease, which disagree when one write fails; the package would read a lease it didn't take from a table it doesn't own the semantics of.

### Option C: The lease enforced by core

Core would refuse an edit by anyone but the lease's holder.

**Cons:** core is pure ([ADR-0001](0001-python-library-with-sans-io-core.md)) and has no clock, and an expiry needs one; a lease held by a crashed holder would block every surface until it lapsed.

### Option D: Proposals queued behind the lease

An agent's edit made while someone holds the lease would be kept as a proposal, to be reviewed after the check-in.

**Cons:** it would be stale on arrival, made against the version before the check-in; the agent plans again instead, against the new head, with the change note ADR-0008 gives it.

## Trade-off analysis

Option A puts the lease where the access checks already are, and asks storage only for what the semantics already kept: the holder and the expiry. Option B avoids one method in a protocol at the cost of two records of the truth. Option C would make the lease binding at the cost of a clock in core, which is the one thing core must not have.

## Consequences

- Easier: one writer at a time for kinds that can't be merged, a person's for hours and an agent's for seconds, with who has it shown to viewers.
- Easier: a busy agent learns at once, before calling anything, and from whom.
- Harder: a storage an application wrote must implement `Storage.lease`.
- Harder: the lease's semantics rest on the processes' clocks agreeing, as thread claims' do. The seconds-long leases of agent edits assume they agree to well under a second.
- The thread claim's spec is unchanged: this lease has no renewal task and fences no write. A model of check-outs and agent edits under it would be a spec of its own (lattice ADR-0025), not written here.

## Action items

1. [x] `Workspace.lease_artifact`, `artifact_lease` and `release_artifact`; `ArtifactLease` and `ArtifactBusy`; `Storage.lease` in both storages; tests over every storage, and a property test against a model of the lease.
2. [x] The package that holds check-outs and agent edits under it: `artifactr-files-ai`.

## Note (2026-10-17): the package is artifactr's `files` extra

`artifactr-files-ai`, named above, was never released: before its first release it became artifactr's `files` extra, `artifactr-ai[files]`, imported as `artifactr.files` ([lattice ADR-0026](../../adr/0026-a-distribution-needs-a-reason-integrations-are-extras.md)). The decision above is unchanged; the rest of artifactr still imports nothing of it.
