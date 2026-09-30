# ADR-0003: A thread is never a chain

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Records decision D3 of [stackr RFC-0002][rfc-0002], the combined system.

## Context

A thread is a conversation that can run for weeks. A chain is one causal story in reflexr, from a first event to everything it caused, identified by its `correlation_id` ([reflexr ADR-0024][r-adr-0024]). reflexr's chain measures, such as time to resolution and cost per chain, assume a chain is short and about one thing.

## Decision

- **Each bridged event from a person starts a chain of its own**, as any source event does.
- **A chain that begins with a thread event carries the thread's id** as a field and as a `thread:` tag.
- **The chain reaches back into the thread** through the proposals and notices it posts there.

## Options considered

| Option | For | Against |
|---|---|---|
| **A thread is never a chain (chosen)** | Chains stay short, and chain measures keep their meaning | Linking the two needs tags |
| A thread is one chain | One id for everything | A chain that lasts weeks. `chain_events` returns the whole thread, and chain measures stop meaning anything |
| A chain per turn | Groups the events one turn caused | The follower has to track turns. Could come later as a refinement |

## Consequences

- Easier: a chain's measures mean the same for bridged events as for any other source.
- Harder: nothing measures a thread together with the chains it started; that is an open question for evalr.

[r-adr-0024]: https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0024-causal-chains-and-operator-actions.md
[rfc-0002]: https://github.com/alexnodeland/stackr/blob/main/docs/rfcs/0002-the-combined-system.md#d3-chains-and-threads
