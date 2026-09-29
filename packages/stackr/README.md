# stackr

The infrastructure template for artifactr, reflexr and evalr: local Supabase, LiteLLM, OpenTelemetry, Grafana LGTM with Pyroscope, and Langfuse.

> **Status:** being built, in the phases of [RFC-0001](docs/rfcs/0001-v0.1-implementation-plan.md). [The architecture](docs/architecture.md) shows what exists today.

Part of a family with [artifactr](https://github.com/alexnodeland/artifactr) and [reflexr](https://github.com/alexnodeland/reflexr).

## Quick start

You need Docker with Compose v2, [uv](https://docs.astral.sh/uv/) and `make`.

```bash
git clone https://github.com/alexnodeland/stackr.git
cd stackr
make env        # .env, with local secrets generated
make up         # start the stack
make smoke      # send test telemetry through it and check it arrives
make down       # stop it, keeping its data
```

Applications send OTLP to `localhost:4317` (gRPC) or `localhost:4318` (HTTP), or to `otel-collector` on the `stackr` Docker network. Grafana is at <http://localhost:3000>, as `admin` with `GRAFANA_ADMIN_PASSWORD` from `.env`.

Run `make` to list every command. [CONTRIBUTING](CONTRIBUTING.md) covers the workflow.

## License

[MIT](LICENSE)
