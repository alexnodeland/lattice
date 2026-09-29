# Collector pipelines

The OpenTelemetry Collector's configuration is `deploy/otel-collector/config.yaml`, mounted read-only into the `otel-collector` service ([Observability](../guides/observability.md#the-collector)). Values such as `${env:STACKR_ENVIRONMENT}` are read from the service's environment, which `compose.yaml` sets from `.env`.

## Pipelines

<!-- generated: collector-pipelines -->

| Pipeline | Receivers | Processors | Exporters |
|---|---|---|---|
| `traces` | `otlp` | `memory_limiter`, `resource/environment`, `batch` | `${env:STACKR_TRACES_EXPORTERS}`: set by `make up` from the profiles |
| `metrics` | `otlp` | `memory_limiter`, `resource/environment`, `batch` | `otlp_http/prometheus` |
| `logs` | `otlp` | `memory_limiter`, `resource/environment`, `batch` | `otlp_http/loki` |

<!-- end generated -->

The traces pipeline's exporters come from `STACKR_TRACES_EXPORTERS`, which `make up` sets from the profiles: `[otlp_grpc/tempo, otlp_http/langfuse]` when the `langfuse` profile runs, and `[otlp_grpc/tempo]` when it doesn't. Compose's default, for plain `docker compose`, is both.

## Components

<!-- generated: collector-components -->

### Receivers

| Receiver | Protocol | Listens on | Notes |
|---|---|---|---|
| `otlp` | `grpc` | `0.0.0.0:4317` |  |
| `otlp` | `http` | `0.0.0.0:4318` | CORS from `http://localhost:*`, `http://127.0.0.1:*` |

### Processors

| Processor | Settings |
|---|---|
| `memory_limiter` | `{check_interval: 1s, limit_percentage: 80, spike_limit_percentage: 25}` |
| `resource/environment` | `{attributes: [{key: deployment.environment.name, value: '${env:STACKR_ENVIRONMENT}', action: insert}]}` |
| `batch` | `{}` |

### Exporters

| Exporter | Endpoint | Sends | Headers |
|---|---|---|---|
| `otlp_grpc/tempo` | `tempo:4317` | OTLP gRPC, without TLS |  |
| `otlp_http/prometheus` | `http://prometheus:9090/api/v1/otlp` | OTLP HTTP, without TLS |  |
| `otlp_http/loki` | `http://loki:3100/otlp` | OTLP HTTP, without TLS |  |
| `otlp_http/langfuse` | `http://langfuse-web:3000/api/public/otel` | OTLP HTTP, without TLS | `Authorization: Basic ${env:LANGFUSE_OTLP_AUTH}`, `x-langfuse-ingestion-version: 4` |

### Extensions

| Extension | Settings |
|---|---|
| `health_check` | `{endpoint: '0.0.0.0:13133'}` |

### The Collector's own telemetry

| Signal | Settings |
|---|---|
| `metrics` | `{level: detailed, readers: [{pull: {exporter: {prometheus: {host: 0.0.0.0, port: 8888}}}}]}` |
| `logs` | `{level: info}` |

<!-- end generated -->

`LANGFUSE_OTLP_AUTH` is base64 of the Langfuse project's public and secret keys, which `make env` derives. Prometheus scrapes the Collector's own metrics on port 8888 for the Collector health dashboard; neither 8888 nor the health check's 13133 is published.

## The file

??? example "The whole file: `deploy/otel-collector/config.yaml`"

    ```yaml
    --8<-- "deploy/otel-collector/config.yaml"
    ```
