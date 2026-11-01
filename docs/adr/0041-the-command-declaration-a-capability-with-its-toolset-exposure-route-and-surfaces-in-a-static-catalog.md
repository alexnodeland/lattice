# ADR-0041: The command declaration: a capability with its toolset, exposure, route and surfaces, in a static catalog

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** [RFC-0014](../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)'s P2, P3 and P4, and its first Tracking item (#916); beside [ADR-0032](0032-the-capability-registry-in-lattice-core-four-tiers-three-effects-and-entry-points.md)

## Context

RFC-0014 makes every action a person can take in portalr a command, declared once, which portalr, an MCP or ACP client and a browser agent all reach. RFC-0011's capability registry already declares the part the enforcer needs: name, version, schemas, tier, effects, reversibility, gate, limits and risk class (ADR-0032). A surface needs more:

- the toolset a client turns on;
- whether a read is also a resource;
- portalr's route that a result links to;
- the surfaces a command is offered on.

The parity test, the schemas and the docs must read every package's commands without a database.

## Decision

- **`lattice_core.commands`**, no extra, importing only the standard library, pydantic and `lattice_core.capabilities`:
  - **`Command`** is a `Capability` plus `toolset`, `exposure`, `route`, `resource` and `surfaces`, as RFC-0014 gives it. It is refused unless:
    - its capability is a `command` capability;
    - its name is `<package>.<name>`, one dot, lowercase, digits and underscores, whose tool name fits MCP's 64 characters;
    - a resource exposure names its URI template, and a URI template is exposed as a resource;
    - it is offered on some surface.
  - **`Toolset`** and **`Surface`** are RFC-0014's literals, and `exposure` is `tool`, `resource`, `both` or **`NotExposed`** with a reason, which the parity test asks for.
  - **`Commands`** is a package's static catalog, `commands()`, with no I/O and no scope. **`Watch`** and **`ResourceChanged`** are what a bound provider answers for resources that change.
  - **`tool_name(name)`** is the MCP tool name, `<package>_<name>`. **`catalog(*catalogs)`** composes catalogs by name, and refuses two commands of one name or of one tool name, such as `a_b.c` and `a.b_c`.
  - **`CONTRACT = "1.0.0"`** and `schemas/commands.v1.json`, as the other contracts have.
- **A breaking change is a new command,** `<package>.<name>_v2`, beside the old one, which is deprecated in its description and kept for a release (RFC-0014's P4).
- **Each package's catalog** comes in its own change: grantr's and artifactr's first (RFC-0014's phase 1), each a `commands` module, published as `schemas/<package>.commands.json`. So does the parity test.

## Options considered

### Option A: A command is a capability plus surface metadata (chosen)

**Pros:** one type for the enforcer and every surface. A command is called only through the enforcer, so grantr, integrations, tiers, limits, taint, approval and audit hold for it as for any capability.
**Cons:** a capability that is no command, such as a connector's action, has no toolset or route until something declares one.

### Option B: Metadata held by portr

**Cons:** portalr and the parity test would read portr's tables to know what a command is, and a package's commands would be declared in two places.

## Consequences

- Easier: a package declares a command once, and the enforcer, portr, portalr's client and the docs each read what they need of it.
- Harder: a command's name and tool name are public. Renaming one is a new command and a deprecation, and `lattice:breaks` sees each catalog once it is published.
- To revisit: whether a capability other than a command (a connector's action, an MCP server's tool) is ever offered through a toolset, which would generalize `Command`.

## Action items

1. [x] `lattice_core.commands` and its schema, tested.
2. [ ] grantr's and artifactr's catalogs, `grantr.commands` and `artifactr.commands`, with their schemas.
3. [ ] The parity test, `tests/test_parity.py`, and `x-lattice-command` on every operation (RFC-0014's P13).

## Amendment (2026-11-01)

`Command` gains `tenant_wide`, false by default, and `lattice_core.commands` moves to contract 1.1.0 ([ADR-0044](0044-tenant-wide-commands-called-with-no-workspace-and-checked-on-the-tenant.md)). A tenant-wide command, such as `artifactr.list_workspaces` or any of grantr's, is called with a scope that names no workspace and is checked on the tenant. It is refused if its route or its resource names `{workspace}`.
