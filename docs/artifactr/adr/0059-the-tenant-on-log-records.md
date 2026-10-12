# ADR-0059: The tenant on log records

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[lattice RFC-0002](../../rfcs/0002-portalr-the-portal.md#each-tenants-observability) has portalr show a tenant its own logs, from a Loki every tenant shares, filtered on one attribute. artifactr's spans and metrics carry `artifactr.tenant.id` already, and stackr's Collector copies it to `tenant.id`. Its log records carried no tenant: a record is logged through Python's `logging`, which knows nothing of tenants, and the span it is logged in is often a database or HTTP span that names none either.

## Decision

- **`configure_telemetry` puts the tenant on log records.** A record logged in a span that names a tenant, or in any span inside one, carries that span's tenant attribute.
- **Two processors do it:** a span processor remembers, for each open span, its own tenant attribute or the one of the span it was opened in; a log record processor copies the current span's onto each record, before it is exported. An attribute the record names itself is kept.
- **A library's tenant attribute is its contribution's name and `.tenant.id`:** `artifactr.tenant.id`, `reflexr.tenant.id`. One `configure_telemetry` handles both libraries, from the contributions it is given, and the contribution port is unchanged. reflexr's `configure_telemetry` does the same, in the same code.
- **A span's attributes are read when a child opens, or a record is logged,** so a tenant named after the span started, as a stream names it once the socket is authorized, reaches the children opened, and the records logged, after it is named. A child opened before then keeps none.

## Options considered

| Option | For | Against |
|---|---|---|
| **Inherited through the span tree, by the SDK's processors (chosen)** | No call site changes; every record in a tenant's work carries it, the database's and the HTTP client's too | Holds an entry per open span |
| A context value set wherever the library opens a tenant's span | Explicit | Every place that opens one changes, in both libraries, and a missed one logs without a tenant |
| The tenant in baggage | One mechanism with the session | Baggage travels on outgoing requests: the tenant would reach model providers |

## Consequences

- Easier: stackr's Collector names every signal's tenant as `tenant.id`, and portalr filters Loki on it.
- Harder: a record logged outside any tenant's span carries no tenant, and portalr doesn't show it to a tenant. Nor does a record logged in a trace the sampler drops: its spans aren't recorded, so they name no tenant.
