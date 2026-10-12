# ADR-0006: What v0.1 includes

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision D6 of [lattice RFC-0001][rfc], identity and access.

## Context

The minimum that closes the open door is the widened hook and built-in roles on tenants and workspaces. Several more parts could come after v0.1, each with its own cost now and later.

## Decision

v0.1 includes, beside the built-in roles:

- **Groups:** a tenant's named sets of users and service principals, granted roles like any subject.
- **Service principals:** a tenant's non-human principals, with keys, for integrations, MCP clients and rules.
- **The permission-matrix test:** each library lists every surface with the action it asks, and grantr prints every role against every action, which the template commits as a snapshot.
- **The audit log** ([ADR-0007](0007-an-append-only-audit-log.md)).
- **Custom roles:** a tenant's own named sets of actions, validated against the catalogs. The built-in roles can't be edited.
- **Row-level security** in every SQL adapter, as a second line of defence.

## Options considered

| Option | For | Against |
|---|---|---|
| **All of these in v0.1 (chosen)** | Applications get the whole model at once, and no part changes the schema later | A larger v0.1 |
| Some of these after v0.1 | Sooner | Integrations wait on keys, and later parts change the storage again |

## Consequences

- Easier: custom roles cost little in the core, where roles already live, and integrations get their own keys from the start.
- Harder: v0.1 is larger than the minimum, by the maintainer's choice. Threads and artifacts, and row-level security, come after the parts everything else needs.

[rfc]: ../../rfcs/0001-grantr-identity-and-access.md#decisions
