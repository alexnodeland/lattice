# Troubleshooting

Start with what is running and what it says:

```bash
make ps             # the Compose services, their state and health
make logs           # follow their logs; or docker compose logs <service>
supabase status     # local Supabase, which make ps doesn't show
```

## Starting the stack

### "required variable ... is missing a value: run make env"

A secret or setting is missing from `.env`. Run `make env`: it adds every setting `.env.example` has that `.env` lacks, and keeps the values already there. `make up` does this itself when `.env.example` is newer than `.env`, so this mostly appears with plain `docker compose`.

### "port is already allocated"

Something else on your machine already listens on one of the stack's ports. Each port is a setting in `.env` (`GRAFANA_PORT`, `MINIO_PORT`, `LITELLM_PORT` and the rest, listed in [Settings in .env](../reference/settings.md)): change it, and run `make up` again. If an application reaches the stack through that port, change its `.env` too.

Local Supabase's ports are set in `supabase/config.toml` instead. If another Supabase project on your machine runs, stop it (`supabase stop` in its directory), or the two collide on 54321 to 54327.

### "network supabase_network_stackr-supabase declared as external, but could not be found"

Compose was run directly, before local Supabase's network existed. `make up` creates it; so does `docker network create supabase_network_stackr-supabase`.

### Supabase's Realtime keeps restarting, or everything is slow

A `DOCKER_DEFAULT_PLATFORM` set for other work makes Docker run the stack's images under emulation, where Supabase's Realtime fails to start. `make` unexports it for every command it runs; if you run `supabase` or `docker compose` yourself, `unset DOCKER_DEFAULT_PLATFORM` first.

### `supabase: command not found`, or `npx` isn't found either

`make` uses an installed Supabase CLI, or runs the version pinned in `versions.env` through `npx`, which needs Node. Install one of them: `brew install supabase/tap/supabase` installs the CLI.

### Langfuse or the gateway takes minutes to become healthy

On the first start they run their database migrations, and their health checks allow two minutes before counting failures. `make up` waits for them. If one never becomes healthy, read its logs: `docker compose logs langfuse-web` or `docker compose logs litellm`.

### `db-init` fails

`db-init` creates Langfuse's and the gateway's databases on the database adapter, so it fails when that adapter isn't reachable:

- **"could not translate host name supabase_db_stackr-supabase"**: local Supabase isn't running. `make up` starts it with the `langfuse` or `gateway` profile; if you ran Compose yourself, run `supabase start` first.
- **With `STACKR_DATABASE=postgres`**, Compose's defaults still point at Supabase: `make up` sets the host and admin password for the plain PostgreSQL adapter, so use `make`.

### After deleting `.env`

A new `.env` has new secrets, but some services only read theirs on their first start: Grafana keeps the admin password it started with. Others can't use their data with new ones: Langfuse's salt and encryption key hash its API keys and encrypt what it stores, and the gateway's salt key encrypts its stored credentials. Restore the old `.env` if you can; otherwise start over with `make reset`, which deletes every data volume.

## Telemetry

### A trace is in Tempo but not in Langfuse

- **The `langfuse` profile must run with `observability`.** Traces reach Langfuse only through the Collector, and `make up` adds Langfuse to the Collector's exporters only when the `langfuse` profile is chosen. If you started profiles one at a time, run `make up` again with both, so the Collector gets its new exporters.
- **The Collector's credentials must match Langfuse's project.** They come from `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`; see [after deleting `.env`](#after-deleting-env). The Collector's logs show the export errors: `docker compose logs otel-collector`.
- **The span attributes.** Langfuse 4 reads a trace's session, user, name and tags from every span; a trace whose attributes are only on its root shows without them.

### A rate panel shows no data

Applications push metrics once a minute by default, so a new series has too few samples for a rate for the first minutes. The Prometheus data source knows samples arrive once a minute, so wait two or three minutes. Check the series exists in Explore first: the name Prometheus gives an OTLP metric is not the OTLP name ([Observability](observability.md#prometheus-metrics)).

### The libraries' dashboards aren't in Grafana

They are mounted from your checkout of lattice, from `packages/artifactr/deploy/grafana/dashboards/` and `packages/reflexr/deploy/grafana/dashboards/`, so start the stack from `packages/stackr/` in a full clone, and check that those directories hold the dashboards' JSON files. Grafana picks up new files within 30 seconds.

## The gateway

| Symptom | Cause |
|---|---|
| HTTP 401 | The key isn't one of the proxy's keys. Applications use a tenant's key from `make tenant`, not a provider's key |
| HTTP 400 naming `prompt-injection` | The guardrail blocked the request, as it should for an injection attempt |
| A model fails, and another answers | Its provider's key is empty or wrong, and the group fell back. Put the key in stackr's `.env` and run `make up` again |
| An error that the budget is exceeded | The tenant's team spent its budget for the period. Raise it in the admin UI, or wait for the period to reset |
| `lmstudio` or `omlx/...` can't connect | The local server isn't listening on the host port in `LM_STUDIO_API_BASE` or `OMLX_API_BASE` |
| The same answer twice | Responses are cached for 10 minutes; identical requests inside that time get the cached answer |

## Applications from the template

### `make install` fails with "git failed ... Git repository"

`make install` installs git hooks, which need a repository. Run `git init` in the application, then `make install` again.

### The app profile can't reach the stack

The app profile joins the stack's two networks and reaches its services by name, so the stack must be running with local Supabase: stackr's default `make up`. With `make up PROFILES=observability`, Supabase isn't running, so the application has neither its database nor the keys that verify its users' tokens.

### Every request is 401

- **No token, or an expired one.** Local Supabase's access tokens last an hour; sign in again.
- **No tenant.** The token's `app_metadata.tenant_id` must be set, which only the admin API, with Supabase's secret key, can do.
- **Another issuer.** `AUTH_ISSUER` must match the token's `iss`: `http://127.0.0.1:54321/auth/v1` for tokens from local Supabase's published port.

### `make smoke-app` fails at once

It needs the default profiles running on local Supabase, and port 8800 free: set `SMOKE_APP_PORT` to use another.

## Starting over

```bash
make reset          # stop everything, and delete every data volume, local Supabase's included
make up
```

`.env` survives `make reset`, so the new stack starts with the same secrets.
