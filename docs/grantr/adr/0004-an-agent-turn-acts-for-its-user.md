# ADR-0004: An agent turn acts for its user

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision D4 of [lattice RFC-0001][rfc], identity and access.

## Context

A thread's agent writes on behalf of whoever is chatting. If it were checked with its own grants, a viewer could make it edit; in the work codebase lattice grew beside, a tool that checked a thread's owner instead of the user acting let a viewer inherit the owner's writes.

## Decision

- **A turn's agent acts for the person whose message started it.** artifactr's `AgentActor` and `ExternalAgentActor` gain `on_behalf_of`, and the run's started event records it.
- **A turn takes messages only up to the first change of author,** so a viewer's message can't ride on an editor's turn.
- **grantr checks the user it acts for, then the agent's own write policy applies,** as it does today. A turn with no user is checked as the agent alone, which the template grants nothing.
- **reflexr's runs act as their rule,** a principal with no grants until someone grants it a role.

## Options considered

| Option | For | Against |
|---|---|---|
| **The user whose message started it, capped by the agent's write policy (chosen)** | The actor a check sees is the one acting, and whoever it acts for | Turns are split at each change of author |
| The agent's own grants, whoever is chatting | Simple | A viewer can make the agent do what the viewer may not |

## Consequences

- Easier: the work codebase's bug is impossible by construction.
- Harder: the `Runner` batches messages by author, and every check has to look through `on_behalf_of`.

[rfc]: ../../rfcs/0001-grantr-identity-and-access.md#decisions
