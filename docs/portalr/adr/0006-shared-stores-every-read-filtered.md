# ADR-0006: Shared stores, every read filtered

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision P6 of [lattice RFC-0002][rfc-0002], portalr, the portal.

## Context

The stack keeps one Langfuse project, one Tempo, one Loki and one Prometheus, shared by every tenant. To show a tenant its own traces and logs ([ADR-0004](0004-native-views-of-a-tenants-observability.md)), portalr must never show it another's. Either the stores are split by tenant on the way in, or every read is filtered on the way out.

## Decision

- **Storage stays shared, and every read is filtered.** portalr adds the tenant to every query it sends.
- **One attribute names the tenant:** `tenant.id`, which the collector copies from the libraries' `artifactr.tenant.id` and `reflexr.tenant.id`, on spans, metrics and log records.
- **One module builds every query,** `portalr.readers`, and nothing else in portalr talks to the tools. Each reader takes a `Tenant` that the router makes only after grantr's check allows the read, never a string from the request, and no user writes TraceQL, LogQL or PromQL.
- **PromQL goes through prom-label-proxy,** on portalr's path only, which rewrites every selector to the tenant portalr names. **Traces come from Tempo only;** Langfuse is read for scores.
- **Each reader is tested where it is built:** a test that builds every query it can send and fails if one lacks the tenant, and a test against a stack seeded with two tenants that reads as one and never sees the other.

## Options considered

| Option | For | Against |
|---|---|---|
| **Shared stores; every read filtered in one module, PromQL through prom-label-proxy, traces from Tempo (chosen)** | No change to how the stack stores telemetry. One place to review | Isolation rests on portalr's readers: a reader that forgets the tenant leaks another tenant's data |
| Separate stores, split on the way in: Tempo, Loki and Mimir tenants, and a Langfuse organization per tenant, routed by the collector | The stores enforce isolation themselves | A tenant's creation provisions every store. Mimir replaces Prometheus. Operators lose the view across tenants |

## Consequences

- Easier: the stack stays as it is, and operators keep one view across tenants.
- Harder: one module, the `Tenant` type, prom-label-proxy and the tests over every query make a leak hard, not impossible.
- To revisit: splitting the stores remains the stronger fix, and the readers' interface doesn't change if it is ever made.

[rfc-0002]: ../../rfcs/0002-portalr-the-portal.md#decisions
