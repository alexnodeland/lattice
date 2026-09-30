# ADR-0002: The outbound actor, an `ExternalAgentActor` per rule

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Records decision D2 of [stackr RFC-0002][rfc-0002], the combined system.

## Context

When a reflexr run acts in artifactr (proposes a change, creates an artifact, posts a notice), artifactr attributes the write to an actor and applies that actor's rules. The actor decides how much power a rule has in a workspace people share, and whom its writes are credited to.

## Decision

- **Each rule acts as its own participant:** `ExternalAgentActor(client_id="reflexr:<rule>", name=<rule>)`, where `<rule>` is the rule's qualified name, such as `ops:runbook-updater`.
- **artifactr's own rules then apply**, as for any outside agent:
  - its writes become proposals under a `propose` write policy, or in a thread in suggest mode
  - it can't resolve its own proposals
  - it can't record run facts
- **relayr never sends `respond_to_proposal`.** Since each rule is a different participant, one rule could otherwise accept another's proposal. The outbound adapter has no way to send it, whatever a rule's allowlist says.

## Options considered

| Option | For | Against |
|---|---|---|
| **`ExternalAgentActor`, one `client_id` per rule (chosen)** | artifactr's proposal rules apply as they do for any outside agent. Attribution is per rule | Rules are different participants, so the adapter must forbid resolving proposals itself |
| `SystemActor` | Simple | Writes apply directly and can record run facts. Far more power than a rule needs |
| artifactr's `AgentActor` | Looks like the thread's agent | Impersonates the chat agent, and mixes up artifactr's runs |
| The rule's approver, as a user | People know who that is | Acts with a person's authority, and misattributes every write |

## Consequences

- Easier: people see which rule wrote what, and review it as they review any outside agent.
- Harder: the adapter carries one prohibition of its own, `respond_to_proposal`, that artifactr can't enforce for it.

[rfc-0002]: https://github.com/alexnodeland/stackr/blob/main/docs/rfcs/0002-the-combined-system.md#d2-the-outbound-actor
