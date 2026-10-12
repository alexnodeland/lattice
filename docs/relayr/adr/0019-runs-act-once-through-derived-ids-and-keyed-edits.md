# ADR-0019: Runs act once, through derived ids and keyed edits

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

A rule's run is retried until it succeeds or runs out of attempts ([reflexr ADR-0041][r-adr-0041]), and an attempt can fail after it has acted in artifactr. [stackr RFC-0002][rfc-0002-outbound] wants each write to land once anyway: ids derived from the run, keyed patches, and, for messages, a read-back from the ledger. Since then artifactr refuses a used message id durably ([artifactr ADR-0045][a-adr-0045]), as it refuses a used proposal, artifact or thread id, and has notices that start and steer no turn ([artifactr ADR-0051](../../artifactr/adr/0051-notices.md)).

## Decision

- **One handle per attempt.** `Outbound.acting(reaction)` returns the attempt's `RunActions`, the same object for a function action and for an agent's tools: `create`, `edit`, `notice`, `create_thread`, `send` and `read`.
- **Every write's ids are derived from what it is,** with the run's id and its last checkpoint: an edit from its artifact and path, a create from its kind and a digest of its data, a notice or message from its thread and a digest of its text, a thread from its title. A count of such writes in the attempt tells two identical writes apart. A retried attempt that makes the same writes, in any order, makes them with the same ids, which matters for an agent, whose model may call its tools in another order, or at once, on a retry.
- **artifactr refuses a repeat,** and a refusal counts as done only when it says the derived id is used: a proposal or an artifact that exists, or a message or a thread, whose only `InvalidState` is a used id. Any other `InvalidState`, such as a proposed edit of an artifact archived meanwhile, fails the run. An edit of an archived artifact is refused before it is tried.
- **No read-back.** artifactr refuses a used message id, so a notice or message is posted once with no record of it in the ledger.
- **An edit sets one value at one JSON Pointer path** (an `add` patch), and is skipped when the artifact already holds the value there. Repeating one changes nothing, not even the artifact's version. An edit made by proposal derives its proposal id too.
- **Rejections:** a `VersionConflict` re-reads the artifact and edits again, three times within the attempt, then fails the attempt to be retried. `NotFound`, `ValidationFailed` and `PatchFailed` are `Refused`, which an agent's tools hand back to the model and which, from a function action, fails the attempt to be retried. Every other refusal, `Forbidden` and `InvalidState` among them, is a permanent `RunFailure`. Each carries the refusal's code as its reason.
- **Notices by default** ([ADR-0007](0007-notices-by-default.md)): `notice` posts `kind="notice"`; `send` goes through artifactr's `Runner.send`, only for a rule its allowlist lets start turns ([ADR-0020](0020-allowlists.md)).

## Options considered

| Option | For | Against |
|---|---|---|
| **Ids derived from the run and what each write is (chosen)** | artifactr's own refusals make every write idempotent, in any order; nothing to store | A model that rephrases a notice, or changes an artifact's data, makes a second one |
| Ids derived from the run and each write's position | Simple, as reflexr's `emit` | An agent whose model calls its tools in another order on a retry duplicates every write |
| The ledger's read-back for messages, as RFC-0002 designed | Worked before artifactr ADR-0045 | A ledger write and a log read per message, for what artifactr now does itself |
| **An edit sets a value at a path (chosen)** | Repeating it changes nothing | A rule can't append, and must name each entry |
| Any patch | Expressive | A retried append appends twice |

## Consequences

- Easier: under retries, a rule's proposal, artifact, thread, notice and message each appear once.
- Harder: a retried agent whose model rephrases its notice, or drafts other data, posts or proposes it again; only the same write is made once.
- Harder: a direct edit retried after someone else changed its value sets the run's value again, since a direct change carries no id that tells an earlier attempt's change from another's.
- Harder: `send` commits its message, then asks for the thread's turn. A process that stops between the two leaves the message untaken until something else asks for the thread; a retry finds the id used and asks nothing. [lattice #80](https://github.com/alexnodeland/lattice/issues/80) asks artifactr for a way to close it.

[a-adr-0045]: ../../artifactr/adr/0045-a-message-id-is-used-once.md
[r-adr-0041]: ../../reflexr/adr/0041-executing-runs.md
[rfc-0002-outbound]: ../../stackr/rfcs/0002-the-combined-system.md#outbound-reflexr-to-artifactr
