# ADR-0020: One tenant attribute, and prom-label-proxy

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[lattice RFC-0002](../../rfcs/0002-portalr-the-portal.md#each-tenants-observability) keeps one Tempo, one Loki and one Prometheus for every tenant, and has portalr filter every read by tenant. artifactr names a tenant as `artifactr.tenant.id`, and reflexr as `reflexr.tenant.id`, on spans, metrics and log records. PromQL has no way to force a filter onto a query: a query that forgets the tenant's label reads every tenant's series.

## Decision

- **The Collector names every signal's tenant as `tenant.id`.** A `transform/tenant` processor, in every pipeline, copies `artifactr.tenant.id` or `reflexr.tenant.id` to `tenant.id` on spans, data points and log records. Tempo keeps it as `span.tenant.id`, Loki as the `tenant_id` structured metadata, and Prometheus as the `tenant_id` label.
- **prom-label-proxy is portalr's path to Prometheus,** in the `observability` profile, at `PROM_LABEL_PROXY_PORT` (9091), bound to `STACKR_BIND`. It takes the tenant from its `tenant_id` parameter and rewrites every selector of every query to it. Grafana keeps its direct data source, for operators.
- **The smoke test checks both:** its trace and log are found by `tenant.id`, and the proxy finds its metric for its tenant and nothing for another.

## Options considered

| Option | For | Against |
|---|---|---|
| **One attribute from the Collector, and the proxy for PromQL (chosen)** | Every store filters on one name; no PromQL can escape its tenant | A service more in the stack |
| Each library's own attribute in every query | No Collector change | Every query names two attributes, and a third library a third |
| Prometheus's own tenancy, through Mimir | Stores split by tenant | Replaces Prometheus; RFC-0002's P6 chose shared stores |

## Consequences

- Easier: portalr's readers filter Tempo, Loki and Prometheus on one name.
- Harder: an application that names its tenant some other way isn't filtered: its telemetry has no `tenant.id`.
