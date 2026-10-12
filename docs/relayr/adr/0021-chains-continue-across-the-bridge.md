# ADR-0021: Chains continue across the bridge

**Status:** Accepted, amended by [ADR-0025](0025-counters-and-how-long-causes-are-kept.md) and [ADR-0026](0026-a-retried-send-asks-again-and-turns-traced-by-their-messages.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:** [ADR-0015](0015-cursors-leases-and-dead-letters-in-the-ledger.md): the ledger also keeps the run behind each write, and a chain continued past the depth limit is dead-lettered

## Context

A rule's write in artifactr is bridged back into reflexr like any other envelope. If it started a chain of its own, two rules that answer each other, or a rule and the agent, would loop for ever. [stackr RFC-0002][rfc-0002-loops] continues the run's chain instead: the ledger maps each write back to the run, and the follower publishes the bridged event with the run's causation, so reflexr's depth limit ends the loop. A person's answer to a rule's proposal joins the chain without adding depth. RFC-0002 maps writes "by their derived ids", but a direct edit carries none, and a turn's id is known only once the runner has started it, while it already runs.

## Decision

- **The outbound adapter records the run behind each write before it makes it,** so the follower, which may bridge the write at once, always finds it: a `Cause` (the run's chain, firing, id and depth) in `relayr_causes`, by what the follower can read off the envelope:
  - a proposal by its id, a created artifact by its id, a notice or message by its id;
  - a direct edit by the rule's actor, the artifact's id and the version the edit makes, `<client id>/<id>@<version>`.
- **A turn a rule's message starts is traced by the follower** when it reads the turn's `run_started`. A turn acts for the author of the messages it carries out, one author per turn, and takes the oldest messages no turn has taken. So a turn acting for a rule's actor carries out the rule's messages since its last turn in the thread, whatever turns for others came between: it continues the chain of the run that posted the last of them (of kind `message`: notices start no turn), recorded by the turn's id. The follower reads back no further than the rule's previous turn. A turn for anyone else starts a chain of its own, even when a rule's message asked for it.
- **The follower continues a chain** by publishing through `caused_by(causation, correlation_id=...)`: the turn's cause first, then the write's. Failing both, an accepted or rejected proposal of a rule's (its `proposal_resolved`, and the artifact event an acceptance makes) joins the proposal's chain with no causation: a person's answer is a new cause.
- **A continued chain past the depth limit is dead-lettered** (`DepthExceeded`), as RFC-0002 says. Rules stop sooner, as reflexr refuses a firing deeper than the limit; the dead letter covers a limit lowered since the run.

## Options considered

| Option | For | Against |
|---|---|---|
| **Causes recorded before the write, by ids on the envelope (chosen)** | The follower never sees a rule's write it can't trace | A write that then fails leaves a cause no envelope will match |
| Causes recorded after the write, by the envelope's `seq` | One key for every write, edits included | The follower, which runs at the same time, often bridges the write first, and the chain is lost |
| A turn's cause recorded by the outbound adapter once `Runner.send` returns | No reading back | The turn already runs, and its first events can be bridged before the record |
| **A turn traced from its `run_started` (chosen)** | Read in log order, so it is always in time | The follower reads back through the thread to the rule's message |
| `run_started` naming the messages its turn carries out | No reading back | artifactr doesn't record them yet: [lattice #81](https://github.com/alexnodeland/lattice/issues/81) |

## Consequences

- Easier: two rules that answer each other stop at reflexr's depth limit, and a proposal's whole story, its review included, is one chain.
- Harder: two runs of one rule that edit the same artifact at the same version race for one cause; the first run to record it keeps it. Its depth differs by at most the runs' difference, so loops still end.
- Harder: `relayr_causes` grows by a row or two per write, and nothing removes them; phase 4 gives the causes a time to live. A proposed edit retried after a version conflict records a cause for each version it tried, and a later run of the same rule whose edit makes one of those versions continues the earlier run's chain.
- Harder: the follower reads back through a thread, 100 envelopes at a time by default (`read_back`), to find the message a rule's turn carries out.

[rfc-0002-loops]: ../../stackr/rfcs/0002-the-combined-system.md#loop-control
