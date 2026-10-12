# ADR-0005: Operators see across tenants

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision P5 of [lattice RFC-0002][rfc-0002], portalr, the portal.

## Context

Some of what the admin UI shows isn't scoped to a tenant: deep links into Langfuse and Grafana, whose UIs show every tenant's data, and the list of every tenant with its spend. Someone has to be allowed to see them, and the work codebase's answer, an admin console with its own user file and password, open when the password wasn't set, is what not to repeat.

## Decision

- **Operators are a grant in grantr,** not a separate login: grantr's `operator` role on the deployment, which lattice RFC-0001's D9 makes an audited grant.
- **portalr's actions** are `portalr:read_telemetry` and `portalr:read_spend` on a tenant, which its `owner` and `admin` roles hold, and `portalr:read_deployment` on the deployment, which `operator` holds. They are in a catalog like the libraries', so the template's permission matrix covers portalr too.
- **Deep links and the tenant list** are returned only to callers allowed `portalr:read_deployment`. Tenant admins see their own tenant, and nothing across tenants.

## Options considered

| Option | For | Against |
|---|---|---|
| **Operators, an audited grant in grantr; tenant admins see their own tenant (chosen)** | One model of access, audited, for everything. The tools' power stays with the people who run the deployment | Someone must grant the first operator (`make operator`) |
| Tenant admins only, with no deep links | Nothing crosses a tenant | Nobody can open the tools from the UI, or see the deployment as a whole |

## Consequences

- Easier: who can see across tenants is answered by grantr's audit log, like every other grant.
- Harder: phases 5 and 6 wait on grantr, whose roles and checks this relies on.

[rfc-0002]: ../../rfcs/0002-portalr-the-portal.md#decisions
