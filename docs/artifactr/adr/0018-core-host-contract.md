# ADR-0018: Core's host contract: needs, commit and record

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[ADR-0001](0001-python-library-with-sans-io-core.md) made core sans-IO and [ADR-0002](0002-single-write-path.md) made every change a command. Implementing core (RFC-0001 phase 1) required deciding exactly how a host and core cooperate, which the earlier ADRs left open:

- How does a host know what state to load before core can decide a command, when some commands (accepting a proposal) only reveal what they touch after their first entity is loaded?
- How can core stay deterministic when commands create things that need ids, and when a write policy silently turns an edit into a proposal?
- Where do facts about agent runs (a run started, a tool was called) go, and who may assert them?
- What do identifiers look like to callers?

## Decision

- **A three-step contract.** `needs(item, actor=, state=)` returns the ids still missing from a `State`. The host loads them (recording absent entities as `None`) and calls `needs` again until nothing is missing. `commit(command, state, actor=)` then returns a `CommitResult` (outcome, entities to save, revisions to append, events to log) or raises a `Rejection`. Calling `commit` without loading what `needs` asked for raises `NotLoaded`, a host bug rather than a rejection.
- **Commands carry every id they create**, including the proposal id to use if a write policy turns the change into a proposal. Identical commands against identical state yield identical results, which is what makes the conformance fixtures possible. Adapters fill in ids that clients omit.
- **A proposal wraps the command it would execute** (`CreateArtifact`, `EditArtifact` or `ArchiveArtifact`). Accepting it runs that command, rebased onto the artifact's current version, with the person's optional `changes` patch layered on top. The resulting change is attributed to the person who accepted it and linked to the proposal.
- **The recorded patch always reproduces the stored data.** When validation normalizes data, or changes are layered on, the event carries a patch computed from the stored before and after states rather than the patch that was submitted.
- **Run facts go through `record`**, a sibling of `commit` for `RunStarted`, `ToolCalled`, `ToolReturned`, `RunPaused`, `RunEnded` and application `AppEvent`s. Only the thread's own agent, or the system, may record facts about that thread's runs.
- **Identifiers are plain strings.** `ArtifactId`, `ThreadId` and the others are transparent type aliases that document intent. Generated ids carry a type prefix (`thr_…`), but any string works.

## Options considered

### State loading

| Option | Complexity | Supports dependent loads |
|---|---|---|
| **An iterative `needs` loop (chosen)** | Low | Yes |
| Core calls a loader callback | Low | Yes, but makes core do I/O through the back door |
| Hosts load "everything relevant" by convention | Lowest | Only by guessing, and every host guesses differently |

### Identifiers

| Option | Type safety | Caller friction |
|---|---|---|
| **Plain strings with aliases (chosen)** | Documentation only | None |
| `NewType` per kind of id | Checked by pyright | Every literal id must be wrapped, e.g. `ThreadId("t1")`, in application code and tests |

## Trade-off analysis

The `needs` loop keeps every rule about what a command touches inside core, where the conformance fixtures can check it, without core performing I/O. `NewType` ids caught nothing in practice, since ids flow in from JSON and databases as strings, but they added a wrapper to every call site. pydantic-ai also types its ids as plain strings.

## Consequences

- Easier: a host is a small loop (`needs`, load, `commit`, save), identical for every storage backend.
- Easier: tests and fixtures are deterministic.
- Harder: a host that skips `needs` fails loudly with `NotLoaded` instead of silently deciding on partial state. That is intended.
- The `describe_change` hook's base annotation is `Any` rather than `Self`, because a `Self`-typed parameter cannot be overridden without breaking substitutability; overrides annotate `before: Self`.

## Action items

1. [x] Implement `needs`, `commit`, `record` and the conformance suite (RFC-0001 phase 1).
2. [x] Implement the host loop in `Workspace.commit` and `Workspace.record` (phase 2).
