# Local Supabase

Local Supabase is the stack's default database adapter, and the identity provider applications verify tokens from. It runs through the Supabase CLI rather than Compose, because the CLI is Supabase's own local workflow and pins its images ([ADR-0002](../adr/0002-local-supabase-through-its-cli.md), [ADR-0009](../adr/0009-local-supabase-as-the-database-adapter.md)).

## The project

The `supabase/` directory is a Supabase CLI project, close to what `supabase init` generates:

- `supabase/config.toml` sets the project id, `stackr-supabase`, and the ports. The id names the containers (`supabase_db_stackr-supabase`) and the network (`supabase_network_stackr-supabase`). It differs from the Compose project's name, `stackr`, because the CLI labels its containers as a Compose project too, and Compose would otherwise treat them as its own orphans. `make validate` checks that every file in the repository, the application template's included, agrees on these names.
- `supabase/seed.sql` is loaded into the `postgres` database on the first start and after every `supabase db reset`. It is empty; add seed data there.

`make` runs the CLI for you: an installed `supabase`, or the version pinned in `versions.env` (`SUPABASE_CLI_VERSION`) through `npx`. CI installs the pinned version. The CLI's version decides Supabase's own image versions, so bumping it is how Supabase is upgraded: change `versions.env`, then run `make up` and `make smoke`.

To run CLI commands yourself, run them from stackr's directory, where `supabase/config.toml` is: `supabase status`, or `npx --yes supabase@<version> status` without an installed CLI.

## When it runs

`make up` runs `supabase start` only when a chosen profile keeps data in PostgreSQL (`langfuse` or `gateway`) and `STACKR_DATABASE` is `supabase`, the default. `make up PROFILES=observability` leaves it off.

| Command | Local Supabase |
|---|---|
| `make up` | Started when a profile needs it |
| `make down` | Stopped, keeping its data (`supabase stop`) |
| `make reset` | Stopped, with its data volumes deleted (`supabase stop --no-backup`) |

`SUPABASE_START_FLAGS` passes flags to `supabase start`. To skip services you don't need, such as Studio and the image proxy:

```bash
make up SUPABASE_START_FLAGS="-x studio,imgproxy"
```

CI starts only what the smoke test uses this way.

## Addresses

| Service | On this machine | On Supabase's network |
|---|---|---|
| The API gateway: Auth, REST, Storage, Realtime, GraphQL | <http://localhost:54321> | `supabase_kong_stackr-supabase:8000` |
| PostgreSQL | `postgresql://postgres:postgres@localhost:54322/postgres` | `supabase_db_stackr-supabase:5432` |
| Studio | <http://localhost:54323> | |
| Mailpit: the emails Auth would send | <http://localhost:54324> | |
| Analytics | <http://localhost:54327> | |

`supabase status` prints these, with the local publishable and secret keys (`PUBLISHABLE_KEY` and `SECRET_KEY` in `supabase status -o env`). They are Supabase's well-known local development values, the same on every machine.

## Networking

Supabase's containers are on `supabase_network_stackr-supabase`, not on `stackr`. `make up` creates that network before `supabase start`, so:

- the CLI joins the network rather than creating it, and `supabase stop` leaves it in place under services that still use it
- the stack's services that use PostgreSQL (`db-init`, Langfuse's web server and worker, and the gateway) join it as well as `stackr`, and reach `supabase_db_stackr-supabase:5432` by name
- the network exists even with the plain PostgreSQL adapter, where it is simply empty, so one `compose.yaml` serves both

A container of your own that needs Supabase by name joins this network too: the application template's app profile and dev container join both. From the host, use the published ports.

## The stack's databases

Langfuse and the gateway each get a role and a database on Supabase's PostgreSQL, created by `db-init` from `deploy/postgres/init.sql` on every `make up`:

| Database | Role | Password |
|---|---|---|
| `langfuse` | `langfuse` | `LANGFUSE_DB_PASSWORD` in `.env` |
| `litellm` | `litellm` | `LITELLM_DB_PASSWORD` in `.env` |

Supabase's `postgres` role is not a superuser, and PostgreSQL 16 and later let a role create a database owned by another only if it can `SET ROLE` to it, so the script first grants itself each role. It runs the same way on plain PostgreSQL. `supabase db reset` and `make reset` delete the database volume; the next `make up` recreates both databases, empty.

## An application's own schema

An application's tables belong in a schema of its own, never `public`. Supabase's Data API serves `public` to anyone with the project's publishable key, and Supabase's default privileges grant the `anon` and `authenticated` roles access to every table the `postgres` role creates there ([ADR-0011](../adr/0011-the-application-template-in-detail.md)). Locally, those keys are well known and the ports listen on every interface.

The application template does this for you: `DATABASE_SCHEMA` (the package's name by default) is created at startup, before the libraries' migrations run, and is every connection's `search_path`. The libraries' tables are prefixed, so artifactr's and reflexr's share one schema without clashing.

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres
DATABASE_SCHEMA=my_app
```

## Sign-in: tokens and keys

Supabase Auth issues each signed-in user an access token, a JWT. The CLI pinned in `versions.env` signs them with an asymmetric key (ES256), and publishes the public key at its JWKS URL; the legacy JWT secret (HS256) signs only the API keys. An application verifies a token against the published keys:

| Setting | Local value | What it checks |
|---|---|---|
| `AUTH_JWKS_URL` | `http://127.0.0.1:54321/auth/v1/.well-known/jwks.json`, or `http://supabase_kong_stackr-supabase:8000/auth/v1/.well-known/jwks.json` on the network | The signature, with the key the token's `kid` names |
| `AUTH_ISSUER` | `http://127.0.0.1:54321/auth/v1` | `iss` |
| `AUTH_AUDIENCE` | `authenticated` | `aud` |
| `AUTH_JWT_SECRET` | Empty | HS256 tokens, from a hosted project still on the legacy secret |
| `AUTH_TENANT_CLAIM` | `app_metadata.tenant_id` | Where the tenant is |

Each algorithm is verified only with its kind of key, and a token must carry `exp`, `sub` and the audience. The user is `sub`. The tenant is in `app_metadata`, which only Supabase's service role can set, so a user can't choose their own tenant: set it when you create the user, with the secret key.

```bash
eval "$(supabase status -o env | grep -E '^(SECRET_KEY|PUBLISHABLE_KEY)=')"
curl -X POST http://127.0.0.1:54321/auth/v1/admin/users \
  -H "apikey: $SECRET_KEY" -H "Authorization: Bearer $SECRET_KEY" -H 'Content-Type: application/json' \
  -d '{"email": "ada@example.com", "password": "a-local-password", "email_confirm": true,
       "app_metadata": {"tenant_id": "acme"}}'
curl -s 'http://127.0.0.1:54321/auth/v1/token?grant_type=password' \
  -H "apikey: $PUBLISHABLE_KEY" -H 'Content-Type: application/json' \
  -d '{"email": "ada@example.com", "password": "a-local-password"}' | jq -r .access_token
```

Locally, email confirmation is off and access tokens last an hour (`supabase/config.toml`). The emails Auth would send, such as password resets, appear in Mailpit.

## The plain PostgreSQL adapter

Set `STACKR_DATABASE=postgres` in `.env` to keep the stack's databases on plain PostgreSQL, the `postgres` profile, instead. `make up` then adds that profile when `langfuse` or `gateway` runs, never starts Supabase, and gives `db-init` and the services the host `postgres` and the admin password `POSTGRES_ADMIN_PASSWORD` from `.env`. It is published on port 55432, bound to `127.0.0.1`.

Without Supabase there is no Auth to issue tokens, so an application needs another OpenID Connect provider for its identity port. CI's smoke test runs the whole stack on both adapters, and the application only on local Supabase.
