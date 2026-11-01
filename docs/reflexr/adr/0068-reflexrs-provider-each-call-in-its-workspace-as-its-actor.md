# ADR-0068: reflexr's provider: each call in its workspace, as its actor

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** [ADR-0067](0067-reflexrs-commands-every-action-a-command-or-listed-with-its-reason.md)'s second action item, and lattice [RFC-0014](../../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)'s binding for reflexr (#916)

## Context

ADR-0067 declared reflexr's catalog, static and unbound. RFC-0014 binds each catalog at the application's composition root: a provider, lattice-core's `Provider`, whose `call` opens the workspace for the caller and carries the command out. Agents, through lattice-core's enforcer, and portr call reflexr's commands only through it. grantr's provider (grantr ADR-0042) and artifactr's (artifactr ADR-0099) set the pattern.

## Decision

- **`reflexr.commands.provider(workspaces)`** returns `ReflexrProvider`, lattice-core's `Provider` and `Commands`. It offers every command of the catalog, the same in every workspace. None is `NotExposed`. Where stored rules are off, installing, updating and archiving one are refused as they are carried out, as reflexr's own surfaces refuse them.
- **A call opens the call's workspace as the call's actor** (`actor_for`), so the workspace's `authorize` checks it again, as it checks every surface:
  - a call through an outside client is that client's `ExternalAgentActor`, for the person it acts for;
  - a person's own call is their `UserActor`;
  - an agent's run or a code session is an outside agent's, for the person it acts for, if any, never a rule's own `AgentActor`.
- **An application can pass an `actor` of its own,** as artifactr's provider allows. `reflexr.list_rules` spans the tenant and opens no workspace, as `Workspaces.rules_for` asks.
- **A change is carried out through `Workspaces.execute`,** under an id of its own, as reflexr's surfaces carry one out. A rejection is raised as `CommandRejected`, whose `payload()` is the rejection as the surfaces send it, and the enforcer reports it as the call's failure.
- **Each answers JSON text:** an outcome, or the models a read returns, as JSON. The MCP server's text stays its own.
- **The catalog's layer imports `reflexr.workspace`.** It opens nothing until a provider is bound, so the parity test and the schema still read the catalog without a database.

## Options considered

### Option A: In `reflexr.commands`, beside the catalog (chosen)

**Pros:** one place names each command and runs it, as grantr's provider does; the arguments' models are the catalog's own.
**Cons:** the catalog's layer depends on the workspace.

### Option B: The MCP server's tools as the provider

**Cons:** they live in the `mcp` extra, take MCP's context and answer MCP's text, and a provider must import without the MCP SDK.

## Consequences

- Easier: an agent, through the enforcer, or portr, through the registry, calls reflexr as its own surfaces do.
- Harder: a command added to the catalog needs its case in the provider, which the provider's tests cover.
- To revisit: the MCP server answering through the provider once portr serves reflexr's tools (#917).
