# ADR-0019: Runs act once, through derived ids and keyed edits

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

A rule's run is retried until it succeeds or runs out of attempts ([reflexr ADR-0027][r-adr-0027]), and an attempt can fail after it has acted in artifactr. [stackr RFC-0002][rfc-0002-outbound] wants each write to land once anyway: ids derived from the run, keyed patches, and, for messages, a read-back from the ledger. Since then artifactr refuses a used message id durably ([artifactr ADR-0045][a-adr-0045]), as it refuses a used proposal, artifact or thread id, and has notices that start and steer no turn ([artifactr ADR-0051](../../artifactr/adr/0051-notices.md)).

## Decision

- **One handle per attempt.** `Outbound.acting(reaction)` returns the attempt's `RunActions`, the same object for a function action and for an agent's tools: `create`, `edit`, `notice`, `create_thread`, `send` and `read`.
- **Every write's ids are derived** from the run's id, its last checkpoint and how many writes the attempt made since, as reflexr's `Reaction.emit` derives event ids. A retried attempt that makes the same writes in the same order makes them with the same ids, and artifactr refuses each again with `InvalidState`, which counts as done. After a checkpoint the count starts again, so a resumed graph never reuses an id.
- **No read-back.** artifactr refuses a used message id, so a notice or message is posted once with no record of it in the ledger.
- **An edit sets one value at one JSON Pointer path** (an `add` patch), and is skipped when the artifact already holds the value there. Repeating one changes nothing, not even the artifact's version. An edit made by proposal derives its proposal id too.
- **Rejections:** a `VersionConflict` re-reads the artifact and edits again, three times within the attempt, then fails the attempt to be retried. Every other refusal (`Forbidden`, `NotFound`, `ValidationFailed`, `PatchFailed`, and `InvalidState` on a direct edit) is a permanent `RunFailure` with the refusal's code as its reason.
- **Notices by default** ([ADR-0007](0007-notices-by-default.md)): `notice` posts `kind="notice"`; `send` goes through artifactr's `Runner.send`, only for a rule its allowlist lets start turns ([ADR-0020](0020-allowlists.md)).

## Options considered

| Option | For | Against |
|---|---|---|
| **Ids derived from the run (chosen)** | artifactr's own refusals make every write idempotent; nothing to store | A write's order within an attempt must not change between attempts |
| The ledger's read-back for messages, as RFC-0002 designed | Worked before artifactr ADR-0045 | A ledger write and a log read per message, for what artifactr now does itself |
| **An edit sets a value at a path (chosen)** | Repeating it changes nothing | A rule can't append, and must name each entry |
| Any patch | Expressive | A retried append appends twice |

## Consequences

- Easier: under retries, a rule's proposal, artifact, thread, notice and message each appear once.
- Harder: an action must make its writes in the same order on every attempt, as it must emit its events.

[a-adr-0045]: ../../artifactr/adr/0045-a-message-id-is-used-once.md
[r-adr-0027]: ../../reflexr/adr/0027-executing-runs.md
[rfc-0002-outbound]: ../../stackr/rfcs/0002-the-combined-system.md#outbound-reflexr-to-artifactr
