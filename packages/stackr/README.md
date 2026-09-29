# stackr

The infrastructure template for artifactr, reflexr and evalr: local Supabase, LiteLLM, OpenTelemetry, Grafana LGTM with Pyroscope, and Langfuse.

> **Status:** being built, in the phases of [RFC-0001](docs/rfcs/0001-v0.1-implementation-plan.md). [The architecture](docs/architecture.md) shows what exists today.

Part of a family with [artifactr](https://github.com/alexnodeland/artifactr) and [reflexr](https://github.com/alexnodeland/reflexr).

## Quick start

You need Docker with Compose v2, [uv](https://docs.astral.sh/uv/), `make`, and the [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) (or Node, to run it through `npx`).

```bash
git clone https://github.com/alexnodeland/stackr.git
cd stackr
make env        # .env, with local secrets generated
make up         # start the stack, with local Supabase
make smoke      # send test telemetry through it and check it arrives
make down       # stop it, keeping its data
```

Applications send OTLP to `localhost:4317` (gRPC) or `localhost:4318` (HTTP), or to `otel-collector` on the `stackr` Docker network.

| Service | Address | Sign in with (from `.env`) |
|---|---|---|
| Grafana | <http://localhost:3000> | `admin`, `GRAFANA_ADMIN_PASSWORD` |
| Langfuse | <http://localhost:3300> | `LANGFUSE_ADMIN_EMAIL`, `LANGFUSE_ADMIN_PASSWORD` |
| Supabase Studio | <http://localhost:54323> | |
| LiteLLM admin UI | <http://localhost:4400/ui> | `admin`, `LITELLM_MASTER_KEY` |

Applications reach models through the gateway at `http://localhost:4400` with a tenant's key: `make tenant NAME=acme` creates one. Provider keys go in `.env`.

Run `make` to list every command. [CONTRIBUTING](CONTRIBUTING.md) covers the workflow.

## Start an application

stackr's [Copier](https://copier.readthedocs.io) template generates an application on artifactr, reflexr or both, already wired to the stack: Supabase sign-in and PostgreSQL, agents on the gateway, OpenTelemetry, feedback as Langfuse scores, evalr experiments, and the family's quality gates.

```bash
uvx copier copy gh:alexnodeland/stackr my-app
cd my-app
make install        # writes uv.lock: commit it
make env && make check
make up             # runs it beside the stack
```

`uvx copier update` brings in the template's later improvements. [The architecture](docs/architecture.md#the-application-template) describes what it generates.

## License

[MIT](LICENSE)
