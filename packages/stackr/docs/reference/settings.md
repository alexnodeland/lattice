# Settings in .env

`.env` holds every setting the stack reads. `make env` (`scripts/setup-env`) creates it from `.env.example`, in the same order and with the same comments, and on every later run keeps the values already in `.env` and adds settings that are new ([Security](../guides/security.md#secrets-live-in-env)).

What `make env` writes for each kind of value in `.env.example`:

| In `.env.example` | In `.env` |
|---|---|
| A plain value | The value, which you may change |
| `generate:hex`, `generate:token`, `generate:uuid`, optionally with a prefix (`generate:token:sk-`) | A fresh random secret, made once and then kept |
| `basic-auth:USER_KEY:PASSWORD_KEY` | base64 of the two settings' values joined by a colon, recomputed on every run |
| Empty | Empty, for you to fill in, such as a provider's key |

Settings in `.env` that `.env.example` doesn't have, such as keys you add, are kept at the end of the file.

The settings, as `.env.example` groups and describes them:

<!-- generated: env-settings -->

### The stack as a whole

The host address published ports bind to. 127.0.0.1 keeps every service reachable from this machine only.

| Setting | In `.env.example` |
|---|---|
| `STACKR_BIND` | `127.0.0.1` |

The deployment environment telemetry is labelled with (deployment.environment.name), when an application doesn't set its own.

| Setting | In `.env.example` |
|---|---|
| `STACKR_ENVIRONMENT` | `local` |

### Observability

Grafana signs in as `admin` with this password.

| Setting | In `.env.example` |
|---|---|
| `GRAFANA_ADMIN_PASSWORD` | Generated: 43 URL-safe characters |

Published ports. Applications send OTLP to the Collector on 4317 (gRPC) or 4318 (HTTP), and profiles to Pyroscope on 4040.

| Setting | In `.env.example` |
|---|---|
| `OTLP_GRPC_PORT` | `4317` |
| `OTLP_HTTP_PORT` | `4318` |
| `PYROSCOPE_PORT` | `4040` |
| `GRAFANA_PORT` | `3000` |
| `PROMETHEUS_PORT` | `9090` |
| `TEMPO_PORT` | `3200` |
| `LOKI_PORT` | `3100` |

### Database: the PostgreSQL port

The PostgreSQL adapter the stack's services keep their databases on:

- `supabase`: local Supabase, started by `make up` through its CLI (default)
- `postgres`: plain PostgreSQL, the `postgres` profile

db-init creates a role and a database for each service on either.

| Setting | In `.env.example` |
|---|---|
| `STACKR_DATABASE` | `supabase` |

The plain PostgreSQL adapter's admin password and published port. Local Supabase's are fixed: `postgres`, on port 54322.

| Setting | In `.env.example` |
|---|---|
| `POSTGRES_ADMIN_PASSWORD` | Generated: 64 hex characters |
| `POSTGRES_PORT` | `55432` |

### The Redis protocol, with Valkey

| Setting | In `.env.example` |
|---|---|
| `REDIS_PASSWORD` | Generated: 64 hex characters |

### Object storage: the S3 port, with MinIO

| Setting | In `.env.example` |
|---|---|
| `S3_ACCESS_KEY_ID` | `stackr` |
| `S3_SECRET_ACCESS_KEY` | Generated: 64 hex characters |
| `S3_REGION` | `auto` |
| `MINIO_PORT` | `9000` |
| `MINIO_CONSOLE_PORT` | `9001` |

### Langfuse

| Setting | In `.env.example` |
|---|---|
| `LANGFUSE_PORT` | `3300` |
| `LANGFUSE_DB_PASSWORD` | Generated: 64 hex characters |
| `CLICKHOUSE_PASSWORD` | Generated: 64 hex characters |

SALT and ENCRYPTION_KEY must never change once Langfuse has data.

| Setting | In `.env.example` |
|---|---|
| `LANGFUSE_SALT` | Generated: 43 URL-safe characters |
| `LANGFUSE_ENCRYPTION_KEY` | Generated: 64 hex characters |
| `LANGFUSE_NEXTAUTH_SECRET` | Generated: 43 URL-safe characters |

Created on first start: an organisation and project, the project's API keys, and an admin user who signs in with this email and password.

| Setting | In `.env.example` |
|---|---|
| `LANGFUSE_INIT_ORG_ID` | `stackr` |
| `LANGFUSE_INIT_PROJECT_ID` | `stackr` |
| `LANGFUSE_PUBLIC_KEY` | Generated: `pk-lf-` and a UUID |
| `LANGFUSE_SECRET_KEY` | Generated: `sk-lf-` and a UUID |
| `LANGFUSE_ADMIN_EMAIL` | `admin@stackr.local` |
| `LANGFUSE_ADMIN_PASSWORD` | Generated: 43 URL-safe characters |

The Collector's credentials for Langfuse's OTLP endpoint, derived from the project's keys.

| Setting | In `.env.example` |
|---|---|
| `LANGFUSE_OTLP_AUTH` | Derived: base64 of `LANGFUSE_PUBLIC_KEY:LANGFUSE_SECRET_KEY`, for HTTP Basic |

### The LLM gateway: LiteLLM

| Setting | In `.env.example` |
|---|---|
| `LITELLM_PORT` | `4400` |

The master key administers the proxy (teams, keys, the admin UI at /ui, as `admin`); applications use team keys from scripts/create-tenant instead.

| Setting | In `.env.example` |
|---|---|
| `LITELLM_MASTER_KEY` | Generated: `sk-` and 43 URL-safe characters |

Encrypts credentials the proxy stores; must never change.

| Setting | In `.env.example` |
|---|---|
| `LITELLM_SALT_KEY` | Generated: 43 URL-safe characters |
| `LITELLM_DB_PASSWORD` | Generated: 64 hex characters |

Provider keys. A model whose key is empty fails; the others still work.

| Setting | In `.env.example` |
|---|---|
| `ANTHROPIC_API_KEY` | Empty |
| `OPENAI_API_KEY` | Empty |
| `GEMINI_API_KEY` | Empty |
| `OPENROUTER_API_KEY` | Empty |

Local model servers on this machine, as the gateway's container sees them.

| Setting | In `.env.example` |
|---|---|
| `LM_STUDIO_API_BASE` | `http://host.docker.internal:1234/v1` |
| `OMLX_API_BASE` | `http://host.docker.internal:4243/v1` |

<!-- end generated -->

## The file

??? example "The whole file: `.env.example`"

    ```bash
    --8<-- ".env.example"
    ```
