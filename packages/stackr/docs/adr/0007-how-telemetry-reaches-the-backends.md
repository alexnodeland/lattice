# ADR-0007: How telemetry reaches the backends

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Applications send OTLP to the Collector, the telemetry port ([ADR-0005](0005-ports-and-adapters-for-the-stack.md)). The Collector then has to deliver each signal to its backend. Traces and logs have one natural route each (Tempo and Loki both accept OTLP), but metrics can reach Prometheus three ways, and the choice decides the names and labels the libraries' dashboards must query. Tempo's metrics generator also produces metrics (span metrics and service graphs), and the stack's own services expose metrics of their own.

## Decision

- **Traces** go to Tempo over OTLP gRPC, and (with the `langfuse` profile) to Langfuse over OTLP HTTP.
- **Metrics** go to **Prometheus's native OTLP receiver** (`/api/v1/otlp`), through the Collector's `otlp_http` exporter.
  - Prometheus translates names with its default strategy: dots become underscores, and counters and units gain suffixes. A counter `artifactr.commands` becomes `artifactr_commands_total`; a histogram `artifactr.commit.duration` in seconds becomes `artifactr_commit_duration_seconds_bucket`, `_sum` and `_count`.
  - `service.name` becomes the `job` label, and `service.instance.id` the `instance` label. Data point attributes become labels, with dots turned into underscores (`smoke.run` becomes `smoke_run`). `deployment.environment.name` and `service.version` are promoted from the resource to every series; other resource attributes stay on `target_info`.
- **Tempo's metrics generator** remote-writes span metrics (`traces_spanmetrics_*`) and service graphs (`traces_service_graph_*`) to Prometheus's remote-write receiver, with exemplars, because remote write is what Tempo supports.
- **Logs** go to Loki's OTLP endpoint (`/otlp`). Loki indexes a few resource attributes (such as `service_name`) as labels and keeps the rest, including `trace_id`, as structured metadata.
- **The stack's own services** (the Collector, Prometheus, Tempo, Loki, Pyroscope, Grafana) are scraped by Prometheus, so their health appears next to the applications'.

## Options considered

### Metrics to Prometheus

| Option | Moving parts | Names and labels | Status |
|---|---|---|---|
| **Prometheus's OTLP receiver (chosen)** | The Collector's core `otlp_http` exporter (stable) | Prometheus's own OTLP translation, configurable in `prometheus.yml` (`otlp:`) | Built into Prometheus 3, enabled by a flag |
| The Collector's `prometheus_remote_write` exporter | A contrib exporter (beta) | The exporter's translation | Mature on the Prometheus side |
| The Collector's `prometheus` exporter, scraped | A contrib exporter (beta), a second hop, and a scrape interval of delay | The exporter's translation, with staleness from scraping | A pull model in a push pipeline |

## Trade-off analysis

The OTLP receiver keeps one protocol from the application to Prometheus, uses only the Collector's stable core exporters, and puts the naming rules in one file that Prometheus owns. The other two routes each add a beta contrib exporter, and scraping also adds delay and a pull step in a push pipeline. The cost is that Prometheus's OTLP handling is newer than remote write, so a Prometheus upgrade could change translation details; the smoke test checks the translated name of a counter to catch that.

## Consequences

- Easier: the libraries' dashboards can rely on one documented translation, with names like `artifactr_commands_total` and `reflexr_runs_total`, and `job` equal to the service name.
- Easier: switching metrics to another OTLP backend is a change of one exporter.
- Harder: the name translation is a contract with the libraries' dashboards. A change to Prometheus's `otlp:` settings is a breaking change for them.
- Revisit: native histograms, and UTF-8 names without translation, once the libraries' dashboards want them.

## Action items

1. [x] The Collector's pipelines and Prometheus's receivers (RFC-0001 phase 1), checked by the smoke test.
2. [ ] The Langfuse route for traces (phase 2).
