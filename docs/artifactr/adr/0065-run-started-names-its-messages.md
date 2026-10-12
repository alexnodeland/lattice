# ADR-0065: `run_started` names its messages

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

relayr continues a rule's causal chain into the agent turns a rule's message starts ([relayr ADR-0021](../../relayr/adr/0021-chains-continue-across-the-bridge.md)), so it has to know which messages a turn carries out. `run_started` names the run and its trigger, not its messages. relayr's follower reads back through the thread to the rule's latest message, which relies on the runner taking one author's oldest untaken messages per turn ([ADR-0057](0057-a-turn-acts-for-one-author.md)) ([lattice #81](https://github.com/alexnodeland/lattice/issues/81)).

## Decision

- **`RunStarted.message_ids: tuple[MessageId, ...] = ()`** names the messages the start carries out, oldest first, as the runner planned the turn ([ADR-0055](0055-turns-from-the-log.md)):
  - a new run, the message that starts it;
  - a run resumed by a reply, that message;
  - a run resumed once its requests are answered, the messages it takes as its prompt, which may be none.
- **Messages that reach the run later,** through its watcher, are not named: they steer a turn that has started. A reader that finds no `run_started` naming a message reads it as one of two things: it steered the run that held the thread when it was posted, which the log's next `run_ended` of that run closes, or no turn will take it, because its author may not start one (ADR-0057) and the runner passed it over.
- **`Session.message_ids`** carries them from the runner to the capability, which records `run_started`. A run started outside the runner names none.
- **The field has a default,** so stored `run_started` envelopes load as before, with no migration.

## Options considered

| Option | For | Against |
|---|---|---|
| **The message ids (chosen)** | A reader looks a turn up by the message it knows, with no read | Steering messages aren't named |
| The `seq` range the turn takes | Covers every envelope taken | A reader still reads the log to find the messages in it |
| Name every message the run took, on `run_ended` | Complete | Known only when the run ends, too late for a reader that acts as the turn starts |

## Consequences

- Easier: relayr finds a turn's chain from its `run_started` alone. Its change is the relayr agent's.
- Harder: `run_started` grows by the ids it names, one or a few per turn.
