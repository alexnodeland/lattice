# ADR-0007: An append-only audit log

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision D7 of [lattice RFC-0001][rfc], identity and access.

## Context

Changes to access need a record that admins can read: who granted what, to whom, and when. Telemetry already carries a copy of what happens, but its retention and its readers are the stack's, not a tenant's.

## Decision

- **grantr records every change to access as a typed event** in its own append-only log, with a sequence number, the actor and the time, in the shape of artifactr's and reflexr's logs: tenants, members, groups, roles, grants, keys and restrictions.
- **Refusals aren't recorded;** they are counted in telemetry and logged at the debug level, so a busy client can't fill the log.
- **It is read through grantr's API,** paged by sequence number, and each event also goes to telemetry.

## Options considered

| Option | For | Against |
|---|---|---|
| **An append-only log in grantr (chosen)** | Admins read it in portalr, from the same store as the grants it describes | One more table |
| Telemetry only | Nothing new to store | Retention and access are the stack's, and a tenant's admins can't read it |

## Consequences

- Easier: portalr's admin UI shows a tenant's history of access from one paged read.
- Harder: every command that changes access appends its event in the same transaction.

[rfc]: ../../rfcs/0001-grantr-identity-and-access.md#decisions
