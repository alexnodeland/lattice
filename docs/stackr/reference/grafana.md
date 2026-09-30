# Grafana provisioning

Grafana is provisioned entirely from `deploy/grafana/`, mounted read-only: data sources from `provisioning/datasources/`, dashboard providers from `provisioning/dashboards/`, and the dashboards themselves from `dashboards/` ([Observability](../guides/observability.md#grafana)).

## Data sources

Every data source has a fixed uid, which dashboards and links refer to, and none can be edited in the UI. `make validate` checks that every dashboard refers only to these uids.

<!-- generated: grafana-datasources -->

| Data source | uid | Type | URL | Default | Settings |
|---|---|---|---|---|---|
| Prometheus | `prometheus` | `prometheus` | `http://prometheus:9090` | yes | `httpMethod: POST`, `prometheusType: Prometheus`, `timeInterval: 60s` |
| Tempo | `tempo` | `tempo` | `http://tempo:3200` | no | none |
| Loki | `loki` | `loki` | `http://loki:3100` | no | none |
| Pyroscope | `pyroscope` | `grafana-pyroscope-datasource` | `http://pyroscope:4040` | no | none |

<!-- end generated -->

## Links between signals

<!-- generated: grafana-links -->

| From | To | Shows |
|---|---|---|
| Prometheus: an exemplar's `trace_id` | `tempo` | The trace that produced it |
| Prometheus: an exemplar's `traceID` | `tempo` | The trace that produced it |
| Tempo: a span | `loki` | Its service's logs (`service.name` as `service_name`), from -5m to +5m around it, filtered by trace id |
| Tempo: a span | `prometheus` | Its service's span metrics: Request rate, Error rate, Latency (p95) |
| Tempo: a span | `pyroscope` | Its service's profile, `process_cpu:cpu:nanoseconds:cpu:nanoseconds` |
| Tempo: service map and node graph | `prometheus` | Tempo's service graph metrics |
| Loki: a log line's `trace_id` | `tempo` | The trace |

<!-- end generated -->

A span's link to its service's metrics offers three queries over Tempo's span metrics, where `$__tags` is the span's service:

<!-- generated: grafana-span-metrics -->

| Query | PromQL |
|---|---|
| Request rate | `sum(rate(traces_spanmetrics_calls_total{$__tags}[5m]))` |
| Error rate | `sum(rate(traces_spanmetrics_calls_total{$__tags, status_code="STATUS_CODE_ERROR"}[5m]))` |
| Latency (p95) | `histogram_quantile(0.95, sum by (le) (rate(traces_spanmetrics_latency_bucket{$__tags}[5m])))` |

<!-- end generated -->

## Dashboards

Each directory under `deploy/grafana/dashboards/` is a folder in Grafana. `stackr/` is committed; the libraries' folders, `artifactr/` and `reflexr/`, are downloaded by `make dashboards` at the releases pinned in `versions.env`, and gitignored.

<!-- generated: grafana-dashboards -->

| Provider | Path | A folder per directory | Editable in the UI | Rescanned |
|---|---|---|---|---|
| `stackr` | `/var/lib/grafana/dashboards` | yes | no | every 30s |

**Collector health** (`stackr-collector`), from `deploy/grafana/dashboards/stackr/collector.json`:

| Row | Panels |
|---|---|
| Overview | Spans accepted; Metric points accepted; Log records accepted; Refused; Export failures; Queue usage |
| Receivers | Accepted, by receiver; Refused or failed, by receiver |
| Exporters | Sent, by exporter; Send failures, by exporter; Sending queue, by exporter; Batches sent, by trigger |
| Process | Memory; CPU; Scrape targets up |

<!-- end generated -->

## The files

??? example "The whole file: `deploy/grafana/provisioning/datasources/datasources.yaml`"

    ```yaml
    --8<-- "packages/stackr/deploy/grafana/provisioning/datasources/datasources.yaml"
    ```

??? example "The whole file: `deploy/grafana/provisioning/dashboards/dashboards.yaml`"

    ```yaml
    --8<-- "packages/stackr/deploy/grafana/provisioning/dashboards/dashboards.yaml"
    ```
