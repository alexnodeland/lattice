# ADR-0005: Ports and adapters for the stack

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Applications on artifactr, reflexr and evalr need telemetry backends, an LLM gateway, a database, object storage and identity. stackr picks a default for each: Tempo, Prometheus, Loki, Pyroscope and Langfuse; the LiteLLM proxy; local Supabase; MinIO. Each of those defaults will be replaced somewhere: by a hosted service in production, by plain PostgreSQL where Supabase isn't wanted, by another S3 store. If applications or the libraries talk to a vendor directly, every such swap becomes a code change in every application.

The libraries already follow this shape in code: they depend on the OpenTelemetry API only, reach models through pydantic-ai's OpenAI-compatible provider, and take storage through a protocol. The stack should give them the same shape at the infrastructure level.

## Decision

- **Applications talk only to ports**: a stable protocol at a stable address, configured by a small set of settings. Behind each port sits an **adapter**, the service that implements it. stackr ships a default adapter for each port and documents the alternatives.
- **Swapping an adapter changes stackr's configuration, never an application's.** A different telemetry backend is a change to the Collector's exporters; a different model provider is a change to the proxy's configuration; a different database is a different connection string.
- **Compose profiles are adapter sets.** `observability` and `langfuse` are the default telemetry adapters behind the Collector, `gateway` is the LLM port with its provider routes, and local Supabase (or a plain PostgreSQL profile) is the database adapter.
- **The ports:**

| Port | Contract | Settings an application reads | Default adapter | Alternative adapters |
|---|---|---|---|---|
| Telemetry | OTLP to the OpenTelemetry Collector: gRPC on 4317, HTTP on 4318 | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` | The Collector, exporting traces to Tempo and Langfuse, metrics to Prometheus and logs to Loki | Any OTLP backend, by changing the Collector's exporters: a hosted Grafana stack, Langfuse Cloud, Jaeger, Honeycomb, Logfire |
| Profiles | Pyroscope's push API | `PYROSCOPE_SERVER_ADDRESS` | Pyroscope | Any Pyroscope-compatible endpoint, such as Grafana Cloud Profiles |
| LLM gateway | An OpenAI-compatible HTTP API; models are named by alias or group (`default`), never by provider | `LITELLM_BASE_URL`, `LITELLM_API_KEY` (a team's virtual key); for OpenAI SDKs, `OPENAI_BASE_URL` and `OPENAI_API_KEY` | The LiteLLM proxy, routing to Anthropic, OpenAI, Gemini, OpenRouter and local model servers | Another OpenAI-compatible gateway; providers change in the proxy's configuration |
| Database | A PostgreSQL connection string | `DATABASE_URL` | Local Supabase's PostgreSQL | Plain PostgreSQL, hosted Supabase, any managed PostgreSQL |
| Object storage | The S3 API | `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_FORCE_PATH_STYLE` | MinIO | AWS S3, Cloudflare R2, Supabase Storage's S3 endpoint |
| Identity | JWTs, verified against the issuer's JSON Web Key Set | `AUTH_ISSUER`, `AUTH_JWKS_URL`, `AUTH_AUDIENCE` | Supabase Auth | Any OpenID Connect provider |
| Evaluation data | Langfuse's public API, for scores and datasets | `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | Self-hosted Langfuse | Langfuse Cloud |

- **Internal ports** connect the stack's own services and are not for applications: the Redis protocol (Langfuse's queues, the proxy's routing state), ClickHouse (Langfuse), and the same PostgreSQL and S3 ports above, which Langfuse and the proxy use like any application.
- **Two ports are narrower than the rest,** and are named as such:
  - **Profiles** go to Pyroscope's API directly, because OTLP profiles are still experimental in the Collector. When that signal is stable, profiles move behind the telemetry port.
  - **Evaluation data** is Langfuse's own API. Traces never use it (they go through the Collector); only the libraries' `[langfuse]` extras call it, for scores and datasets, and those extras are the adapter on the library side.
- **The application template generates applications wired to these ports only**, reading exactly the settings in the table.

## Options considered

| Option | Swapping a backend | Application configuration | Vendor features |
|---|---|---|---|
| **Ports with default adapters (chosen)** | A change in stackr's configuration | The same settings everywhere | Through the port's protocol, plus the two narrow ports |
| Applications use each vendor's SDK and endpoint | A code change in every application | One set per vendor | All of them, directly |
| An abstraction service of our own in front of everything | A change in that service | One API | Only what we re-expose, and one more service to maintain |

## Trade-off analysis

The ports are open protocols that the defaults already speak (OTLP, the OpenAI API, PostgreSQL, S3, JWT), so the cost is discipline rather than code: no application setting may name a vendor's endpoint. A vendor-only feature (a LiteLLM-specific request field, a Langfuse score) is still reachable, but through a documented extension of the port (the proxy's metadata and guardrail fields in the request body) or a named narrow port.

## Consequences

- Easier: moving an application from the local stack to production services is a change of settings, and the same application runs against local Supabase or plain PostgreSQL.
- Easier: the Collector is the one place telemetry is routed, filtered and enriched.
- Harder: the settings in the table are a contract with the libraries' extras and the application template. Renaming one is a breaking change for them.
- Revisit: move profiles behind the Collector when OTLP profiles are stable.

## Action items

1. [ ] Telemetry and profiles ports, with the observability adapters (RFC-0001 phase 1).
2. [ ] The Langfuse adapter behind the Collector, and the object storage and evaluation data ports (phase 2).
3. [ ] The database port, with local Supabase and plain PostgreSQL as adapters (phase 3).
4. [ ] The LLM gateway port (phase 4).
5. [ ] The identity port, and an application template wired to the ports only (phase 5).
