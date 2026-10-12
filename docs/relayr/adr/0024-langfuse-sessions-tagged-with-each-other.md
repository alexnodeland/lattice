# ADR-0024: Langfuse sessions tagged with each other

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:** [ADR-0013](0013-relayr-in-lattice.md): relayr's `langfuse` extra needs evalr

## Context

In Langfuse, a thread is artifactr's session, and a causal chain is reflexr's ([ADR-0004](0004-sessions-linked-not-continued.md)). D4 joins them with tags: a run that starts from a thread event is tagged `thread:<id>`, and a turn relayr starts is tagged `chain:<correlation id>` and `rule:<name>`. The Langfuse user of a run started from a bridged event is the event's author, not relayr's source. Each library takes a context entered around every turn or run, and offers its Langfuse attributes as `turn_attributes(session)` and `run_attributes(reaction)`.

## Decision

- **`relayr.langfuse.bridged_run`** is a reflexr `RunContext`, given to the reactor in place of `langfuse_run`. It propagates reflexr's run attributes, adds `thread:<id>` for each thread of the bridged events that made the rule fire, and sets the user to the person who acted in artifactr, when a person did.
- **`relayr.langfuse.bridged_turns(ledger)`** returns an artifactr `TurnContext`, given to the `Runner` in place of `langfuse_turn`. It propagates artifactr's turn attributes. For a turn that acts for a rule's actor, it adds `rule:<name>`, and `chain:<correlation id>` for the run behind the rule's message that the turn carries out.
- **The turn's chain is found the way the follower finds it** ([ADR-0021](0021-chains-continue-across-the-bridge.md)): by reading the thread back to the rule's last message, whose run the outbound adapter recorded before it sent it. `relayr.outbound.turn_cause` is that one function, which both use. The turn's context is entered as the turn starts, before the follower has traced it, so reading back from the message is what makes the tag certain.
- **Both are behind the `langfuse` extra,** which installs the libraries' own `[langfuse]` extras, and so evalr. relayr names `evalr[langfuse]` in it and takes evalr from the workspace, as the libraries do, so its wheel is built and installed with relayr's; ADR-0013's "relayr requires no extra that needs evalr" no longer holds.
- **LiteLLM's metadata doesn't carry the tags yet.** The libraries' gateways build it from their own fields and fixed tags. [lattice #86](https://github.com/alexnodeland/lattice/issues/86) asks them to take the propagated tags, which would need nothing from relayr.

## Options considered

| Option | For | Against |
|---|---|---|
| **Wrap the libraries' attributes (chosen)** | Their sessions, users and metadata stay theirs; relayr adds only what joins them | The application gives relayr's contexts in place of the libraries' |
| One Langfuse session for a thread and its chains | One view | D4 ruled it out |

## Consequences

- Easier: from a thread's session, Langfuse finds the chains it started by tag, and from a chain, the turns it started.
- Harder: the turn context reads the thread back once per turn that acts for a rule.
