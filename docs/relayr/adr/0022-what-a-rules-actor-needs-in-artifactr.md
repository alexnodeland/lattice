# ADR-0022: What a rule's actor needs in artifactr

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:** [lattice RFC-0001](../../rfcs/0001-grantr-identity-and-access.md#the-ports)'s `subject_of` table, two rows: an `ExternalAgentActor` of a rule's is the rule's principal, not a service principal of its own; and artifactr's `AgentActor` acting for a rule's actor is the rule's principal, not the agent with no grants

## Context

A rule's run acts in artifactr as `ExternalAgentActor(client_id="reflexr:<rule>", name=<rule>)` ([ADR-0002](0002-the-outbound-actor-an-external-agent-per-rule.md)). artifactr asks `authorize` for every action, and with grantr wired the template's `subject_of` decides who that actor is ([lattice RFC-0001](../../rfcs/0001-grantr-identity-and-access.md#the-ports)): an `ExternalAgentActor` is the user in its `on_behalf_of`, or else its own principal. grantr's `rule` role ([grantr ADR-0020](../../grantr/adr/0020-the-rule-role.md)) holds a stored rule's reflexr actions only, and notes that a rule that writes in artifactr needs more, granted separately. grantr's phase 4 and 5 grant it, so they need the list.

## Decision

- **A rule's actor acts for no person:** its `on_behalf_of` is None, so `authorize` sees the rule itself.
- **The template's `subject_of` maps it to the rule's principal:** `RulePrincipal(workspace, rule)` for a stored rule, and, for a rule defined in code, the application's own principal, as grantr ADR-0020 has code rules run.
- **A turn a rule's message starts acts for the rule:** its agent's `on_behalf_of` is the rule's actor, so `subject_of` maps that agent to the rule's principal too, and the turn's writes are checked as the rule's, under the agent's own write policy.
- **What it needs in artifactr,** each on the workspace, or on the thread or artifact the action names:

  | Action | When |
  |---|---|
  | `artifactr:open`, `artifactr:read_artifacts` | Always: a run opens the workspace, and reads an artifact before it edits it |
  | `artifactr:propose_change` | Always: writes are proposals by default |
  | `artifactr:post_message` | Always: notices; and the messages that start turns |
  | `artifactr:create_artifact`, `artifactr:edit_artifact` | When its allowlist names kinds in `direct` |
  | `artifactr:create_thread` | When its allowlist has `create_threads` |
  | `artifactr:record` | When its allowlist has `turns`: starting a turn asks it, as the agent acting for the rule |

- **It never needs `artifactr:respond_to_proposal`,** which relayr has no way to send ([ADR-0002](0002-the-outbound-actor-an-external-agent-per-rule.md)), nor archiving or feedback, which the outbound adapter doesn't make.

## Options considered

| Option | For | Against |
|---|---|---|
| **The rule's own principal, granted these actions (chosen)** | Each rule holds what it does, and its writes are its own in the audit log | A role of artifactr actions to define beside grantr's `rule` |
| The application's principal for every rule | No grant per rule | Every rule could do what any rule may; the allowlist would be the only limit left |
| The person who installed the rule, as `on_behalf_of` | Their grants already exist | Acts with a person's authority, which D2 ruled out |

## Consequences

- Easier: grantr's phase 4 and 5 have the complete list, and the allowlist and the grants say the same thing in two places that check each other.
- Harder: a rule needs two grants, its `rule` role in reflexr and these actions in artifactr, until grantr defines one role for both.
