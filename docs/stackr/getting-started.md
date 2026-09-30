# Getting started

This page starts the stack on your machine, finds each service's interface, checks that telemetry flows through it, and then generates an application from the template and runs it beside the stack.

## Prerequisites

| Tool | Why |
|---|---|
| Docker, with Compose v2 (`docker compose version`) | Runs the stack. Its images are multi-architecture and run natively on Intel and Apple silicon. |
| [uv](https://docs.astral.sh/uv/) | Runs stackr's scripts and tools at the versions in `uv.lock`, and Copier through `uvx`. |
| `make` and `git` | Every command is a `make` target. |
| The [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) (`brew install supabase/tap/supabase`), or Node | Runs local Supabase. Without an installed `supabase`, `make` runs the version pinned in `versions.env` through `npx`. |
| `curl` and `jq` | `make validate`, the smoke tests, and the examples on this page. |

The first start pulls several gigabytes of images.

## Start the stack

```bash
git clone https://github.com/alexnodeland/lattice.git
cd lattice/packages/stackr
make env
make up
```

`make env` runs `scripts/setup-env`, which copies `.env.example` to `.env` and replaces every `generate:...` placeholder with a fresh secret: Grafana's admin password, database passwords, Langfuse's keys, the gateway's master key and the rest. `.env` is gitignored and written with mode 0600. Running `make env` again keeps every value already in `.env` and adds settings that are new in `.env.example`, so it is safe after every pull. [Settings in .env](reference/settings.md) lists them all.

Provider keys are the only settings you fill in yourself, and only for the providers you use: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` and `OPENROUTER_API_KEY` in `.env`. The stack starts without them, and the smoke tests don't need them.

`make up` then:

1. creates local Supabase's Docker network, `supabase_network_stackr-supabase`, if it doesn't exist
2. runs `supabase start`, because the `langfuse` and `gateway` profiles keep data in PostgreSQL
3. runs `docker compose` with the `observability`, `langfuse` and `gateway` profiles, and waits until every service with a health check is healthy

Langfuse and the gateway run their database migrations on the first start, so the first `make up` takes a few minutes.

### Choosing profiles

`PROFILES` chooses what runs; the default is all three:

```bash
make up PROFILES=observability              # the Collector, Tempo, Prometheus, Loki, Pyroscope and Grafana
make up PROFILES="observability gateway"    # add the LLM gateway, and local Supabase for its database
```

Local Supabase starts only with a profile that needs PostgreSQL (`langfuse` or `gateway`), so `make up PROFILES=observability` runs Compose alone. To keep the stack's databases on plain PostgreSQL instead of Supabase, set `STACKR_DATABASE=postgres` in `.env`. [The stack and its profiles](guides/stack.md) covers both.

### See what is running

```bash
make ps         # the Compose services, with their state and ports
make logs       # follow their logs
supabase status # local Supabase's services, URLs and local keys
```

Run `supabase` commands from stackr's directory, where `supabase/config.toml` is. Without an installed CLI, run the pinned one through `npx`: `npx --yes supabase@<version> status`, with `SUPABASE_CLI_VERSION` from `versions.env`.

## Where each service lives

Every published port is bound to `127.0.0.1`, and each is a setting in `.env` in case it collides with something else on your machine.

| Service | Address | Sign in with |
|---|---|---|
| Grafana | <http://localhost:3000> | `admin` and `GRAFANA_ADMIN_PASSWORD` from `.env` |
| Langfuse | <http://localhost:3300> | `LANGFUSE_ADMIN_EMAIL` (`admin@stackr.local`) and `LANGFUSE_ADMIN_PASSWORD` |
| LiteLLM's admin UI | <http://localhost:4400/ui> | `admin` and `LITELLM_MASTER_KEY` |
| Supabase Studio | <http://localhost:54323> | No sign-in, locally |
| Mailpit, the emails Supabase Auth would send | <http://localhost:54324> | |
| Prometheus | <http://localhost:9090> | |
| MinIO's console | <http://localhost:9001> | `S3_ACCESS_KEY_ID` (`stackr`) and `S3_SECRET_ACCESS_KEY` |

And the APIs applications and tools use:

| Port | Address on this machine | On the `stackr` network |
|---|---|---|
| OTLP, gRPC and HTTP | `localhost:4317`, <http://localhost:4318> | `otel-collector:4317`, `otel-collector:4318` |
| Pyroscope's push API | <http://localhost:4040> | `pyroscope:4040` |
| The LLM gateway (OpenAI-compatible) | <http://localhost:4400> | `litellm:4000` |
| Langfuse's public API | <http://localhost:3300> | `langfuse-web:3000` |
| Supabase's API (Auth, REST, Storage, Realtime) | <http://localhost:54321> | `supabase_kong_stackr-supabase:8000`, on Supabase's network |
| Supabase's PostgreSQL | `postgresql://postgres:postgres@localhost:54322/postgres` | `supabase_db_stackr-supabase:5432`, on Supabase's network |
| Tempo, Loki | <http://localhost:3200>, <http://localhost:3100> | `tempo:3200`, `loki:3100` |
| MinIO's S3 API | <http://localhost:9000> | `minio:9000` |

Local Supabase's ports are the exception to `127.0.0.1`: its CLI publishes them on every interface. [Security](guides/security.md) says what to do about that on a shared network. [Compose services and profiles](reference/compose.md) lists every service's ports and settings.

## Check it works

```bash
make smoke
```

The smoke test sends a trace, a metric and a log through the Collector and finds each in Tempo, Prometheus and Loki; sends a trace with a known id and finds it in Langfuse; sends a mocked request through the gateway on a new tenant's key and checks its routing, guardrails, price and trace; and checks the stack's databases on local Supabase. It needs no provider key. It checks the profiles in `PROFILES`, as `make up` does. [The smoke tests](guides/smoke-tests.md) describes every check.

## Give a tenant a key

Applications call the gateway with a tenant's key, never the master key:

```bash
make tenant NAME=acme
```

This creates the team `tenant-acme`, with a budget of 10 USD every 30 days, and a key for it, and prints the two settings an application reads:

```text
LITELLM_BASE_URL=http://127.0.0.1:4400
LITELLM_API_KEY=sk-...
```

The key is shown only once. Running it again keeps the team, and creates another key only for a new `--key-alias`. [The LLM gateway](guides/gateway.md) covers budgets, rate limits and models.

## Generate an application

The template asks a few questions (the name, which libraries, whether to include evals) and generates an application wired to the stack:

```bash
cd ../../..         # out of the clone of lattice
uvx copier copy gh:alexnodeland/lattice my-app
cd my-app
git init            # the git hooks and `copier update` need a repository
make install        # the dependencies, which writes uv.lock (commit it), and the git hooks
make env            # .env, from .env.example
```

Copier takes the latest tag that is a version. lattice's tags carry their package's name, as in `artifactr-v0.1.0`, so none is, and Copier warns that it found no tags and uses `main`.

Fill in `.env`, which the application reads:

| Setting | Where it comes from |
|---|---|
| `LITELLM_API_KEY` | `make tenant NAME=acme` in stackr, above |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | stackr's `.env`: the keys of the `stackr` project Langfuse created on its first start |

Everything else defaults to the stack's addresses on this machine. Then:

```bash
make check          # lint, strict types and the tests with 100% coverage: no stack needed
make up             # build the image and run it in the app profile, beside the stack
curl http://localhost:8800/healthz
```

The app profile is the application's own `compose.yaml`. Its service joins the `stackr` network and local Supabase's, and reaches the stack's services by name, so `make up` in the application needs the stack running with local Supabase: stackr's default `make up`.

### Sign in and call it

The libraries' surfaces need a Supabase access token whose `app_metadata.tenant_id` names the tenant. Create a user of the tenant `acme` with local Supabase's admin API, then sign in:

```bash
eval "$(cd ../stackr && supabase status -o env | grep -E '^(SECRET_KEY|PUBLISHABLE_KEY)=')"
curl -X POST http://127.0.0.1:54321/auth/v1/admin/users \
  -H "apikey: $SECRET_KEY" -H "Authorization: Bearer $SECRET_KEY" -H 'Content-Type: application/json' \
  -d '{"email": "ada@example.com", "password": "a-local-password", "email_confirm": true,
       "app_metadata": {"tenant_id": "acme"}}'
TOKEN=$(curl -s 'http://127.0.0.1:54321/auth/v1/token?grant_type=password' \
  -H "apikey: $PUBLISHABLE_KEY" -H 'Content-Type: application/json' \
  -d '{"email": "ada@example.com", "password": "a-local-password"}' | jq -r .access_token)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8800/artifactr/v1/workspaces/main/artifacts
```

The last request lists a workspace's artifacts, in an application with artifactr; without a token it is refused with 401. The generated `README.md` goes on from here with requests for each library's example. An agent's trace, from the application through the gateway to the model, is in Grafana's Explore (Tempo) and in Langfuse, and the application's metrics are in Prometheus, with `job` set to its slug (`my-app`). [The application template](guides/template.md) describes what was generated and how to keep it up to date.

## Stop

```bash
make down           # in my-app: stop the application
make down           # in stackr: stop the stack and local Supabase, keeping their data
make reset          # in stackr: stop them and delete their data volumes
```
