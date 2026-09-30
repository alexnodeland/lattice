# ADR-0007: Notices by default

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Records decision D7 of [stackr RFC-0002][rfc-0002], the combined system.

## Context

A message that people send through artifactr's surfaces starts a turn: a model call, which can edit artifacts, which can fire rules again. Most rules only need to tell people something ("the rule is live", "the deploy failed"), and a turn per message would cost a model call each time and make loops far more likely.

## Decision

- **A rule's messages are notices by default.** relayr commits them directly, as the rule's actor, without `Runner.send`, so they start no turn.
- **Starting a turn is a per-rule permission**, granted in the rule's allowlist. Only then does relayr send the message through `Runner.send`.

## Options considered

| Option | For | Against |
|---|---|---|
| **Notices by default; starting a turn is a per-rule permission (chosen)** | Most rules only need to inform people. Turns cost model calls and can loop | A rule that needs the agent must say so |
| Every bridge message starts a turn, as messages from the surfaces do | Uniform | Each notice becomes a model call, and loops get much more likely |

## Consequences

- Easier: a rule that reports its work costs nothing in model calls, and can't start a runaway turn.
- Harder: a notice posted while a turn is running still reaches that turn, and nothing marks it as a notice for other clients. [artifactr #63][a-63] closes that gap, and phase 2 waits for it.

[a-63]: https://github.com/alexnodeland/artifactr/issues/63
[rfc-0002]: https://github.com/alexnodeland/stackr/blob/main/docs/rfcs/0002-the-combined-system.md#d7-may-a-rule-start-a-turn
