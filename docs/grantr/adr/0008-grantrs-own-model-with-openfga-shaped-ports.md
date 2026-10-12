# ADR-0008: grantr's own model, with OpenFGA-shaped ports

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision D8 of [lattice RFC-0001][rfc], identity and access.

## Context

Authorization engines exist, and each answers checks and some answer list queries. grantr's model has four resource levels (the deployment, a tenant, a workspace, and a thread, artifact or rule) and no relations deeper than that, and the family keeps a core with no I/O behind ports, with in-memory and SQL adapters and one contract test ([artifactr ADR-0034][a-adr-0034]).

## Decision

- **grantr has its own model,** in a core with no I/O, behind a storage port with an in-memory adapter and an SQL adapter, and one contract test run against both.
- **Its reads are shaped like OpenFGA's:** `check` like `Check`, and `hidden` and `resources` like `ListObjects`, so an OpenFGA adapter could be added if the model outgrows fixed levels. None is planned.
- **Decisions aren't cached across requests.** A check is one indexed query; a request may reuse its own answers.

## Options considered

| Option | For | Against |
|---|---|---|
| **grantr's own model, with OpenFGA-shaped ports (chosen)** | No server to run, testable in memory, one store for the grants and the data they protect | grantr is the place a mistake becomes a breach |
| OpenFGA or SpiceDB | Strong list queries, maintained | A server to run, and every grant written twice |
| Cedar, through `cedarpy` | Embeddable | Takes the entities on every call, and can't list what an actor may see |
| Casbin | Embeddable | Untyped configuration files, and weak filtering |
| Oso or Topaz | Embeddable, or self-hosted | Oso's library is deprecated for its cloud, and Aserto, which made Topaz, has shut down |

## Consequences

- Easier: grantr runs wherever the libraries do, in memory in tests and on the application's database in production.
- Harder: the model is the family's to get right, and the contract test is its guard.

[a-adr-0034]: ../../artifactr/adr/0034-ports-and-adapters-for-integrations.md
[rfc]: ../../rfcs/0001-grantr-identity-and-access.md#decisions
