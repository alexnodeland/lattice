# ADR-0026: A retried send asks again, and turns are traced by their messages

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:**

- [ADR-0019](0019-runs-act-once-through-derived-ids-and-keyed-edits.md): its consequence about `send`'s window.
- [ADR-0021](0021-chains-continue-across-the-bridge.md) and [ADR-0024](0024-langfuse-sessions-tagged-with-each-other.md): how a turn's chain is found.

## Context

Two gaps were left open, each waiting on artifactr:

- **`send`'s window ([ADR-0019](0019-runs-act-once-through-derived-ids-and-keyed-edits.md)).** `send` commits its message, then asks for the thread's turn. A process that stopped between the two left the message untaken, and a retry found its id used and asked nothing.
- **Tracing a turn ([ADR-0021](0021-chains-continue-across-the-bridge.md), [ADR-0024](0024-langfuse-sessions-tagged-with-each-other.md)).** The follower and the Langfuse turn context read the thread back to find the rule's message a turn carries out. The turn context reads before the turn's `run_started` is logged, so a message the rule sent meanwhile could tag the turn with the wrong chain.

artifactr has closed both:

- `Runner.ask` asks for a thread's next turn, covering whatever no turn has taken ([artifactr ADR-0064](../../artifactr/adr/0064-asking-for-a-threads-next-turn.md)).
- `RunStarted.message_ids` names the messages a turn's start carries out, which the `Session` carries too ([artifactr ADR-0065](../../artifactr/adr/0065-run-started-names-its-messages.md)).

## Decision

- **A retried `send` asks again.** When artifactr refuses the derived message id as used, `send` calls `Runner.ask` for the thread. That starts the turn an earlier attempt never asked for, or does nothing if a turn took the message. A refusal from `ask` is handled as one from `send`.
- **A turn's chain is that of the last of its messages that a run posted.** `turn_cause(ledger, workspace, message_ids)` looks them up in the ledger, newest first. The follower passes the `message_ids` of the turn's `run_started`; the Langfuse turn context passes the `Session`'s. Neither reads the thread.
- **`read_back` is gone,** from `Followers` and from `bridged_turns`.

## Options considered

| Option | For | Against |
|---|---|---|
| **The turn's own message ids (chosen)** | Exact, with no read of the thread, and the same in the follower and the turn context | A turn logged before artifactr named its messages continues no chain |
| Read the thread back, as before | Works on any log | A read per turn, and the turn context could pick a message sent after the turn started |
| **`ask` after a used id (chosen)** | Closes the window with one call, which does nothing when a turn took the message | A retry reads the thread once more |
| A ledger record of each asked turn | No call to artifactr | A second record to keep in step with artifactr's |

## Consequences

- Easier: a run that stops after sending its message still gets its turn, on its retry.
- Easier: a turn is tagged with its chain exactly, as the follower records it.
- Harder: a turn whose `run_started` names no messages, such as one logged before artifactr recorded them, starts a chain of its own.
