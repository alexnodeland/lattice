# ADR-0003: The observability and gateway services

**Status:** Accepted; amended by [ADR-0016](0016-stackr-in-lattice.md)
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

The libraries emit OpenTelemetry (API only), send LLM traffic through LiteLLM, and want Langfuse for LLM traces, scores and datasets ([artifactr ADR-0027](https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0027-opentelemetry-observability-with-langfuse.md), [ADR-0031](https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0031-litellm-proxy-first.md)). The tooling should be open.

## Decision

- **An OpenTelemetry Collector** receives all telemetry and fans it out to Tempo, Prometheus, Loki and Langfuse (with the `x-langfuse-ingestion-version: 4` header). Pyroscope receives profiles.
- **Grafana** is provisioned with data sources, cross-links between traces, logs, metrics and profiles, and the libraries' dashboards, pinned by release.
- **Langfuse** is self-hosted, with ClickHouse, MinIO and Redis, and its database on Supabase's PostgreSQL.
- **The LiteLLM proxy** holds model groups, teams per tenant, guardrails and budgets, and sends its own telemetry to the Collector.

## Consequences

- Easier: one trace from a person's request through the application, the gateway and the model, in Grafana and in Langfuse.
- Harder: more services to pin and upgrade.

## Action items

1. [ ] Implement RFC-0001 phases 1, 2 and 4.
