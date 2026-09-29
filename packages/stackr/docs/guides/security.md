# Security

stackr's defaults are for local development and single hosts: secrets generated on each machine, and every service reachable from that machine only. This page says what those defaults are, where they end, and what to change before the stack faces a network you don't trust. To report a vulnerability, follow the [security policy](../project/security.md).

## Secrets live in `.env`

- **Generated, never committed.** `make env` copies `.env.example` to `.env` and replaces each `generate:...` placeholder with a fresh random value: 64 hex characters, 43 URL-safe characters or a UUID, with a prefix where a service expects one (`sk-` for the gateway's master key, `pk-lf-` and `sk-lf-` for Langfuse's keys). `.env` is gitignored and written with mode 0600. `.env.example` holds settings and placeholders only.
- **Stable once made.** Running `make env` again keeps every value already in `.env`, so secrets that encrypt data (`LANGFUSE_SALT`, `LANGFUSE_ENCRYPTION_KEY`, `LITELLM_SALT_KEY`) never change under it. The one value recomputed on every run is `LANGFUSE_OTLP_AUTH`, the Collector's credentials for Langfuse, derived from the project's keys so it always follows them.
- **Required, not empty.** `compose.yaml` refers to each secret as `${NAME:?run make env}`, so Compose refuses to start a service whose secret is missing, rather than starting it with an empty one.
- **Kept off command lines.** Where a secret has to reach a program, it goes through the environment, a file or standard input, never an argument that other processes could read: Valkey writes its password to a config file at start, `db-init`'s script reads the database passwords with `\getenv`, and the smoke test passes keys and passwords to `curl` on standard input.
- **Your own keys.** Provider keys (`ANTHROPIC_API_KEY` and the rest) go in `.env` too, where the gateway reads them. Applications never see them: they call the gateway with a tenant's key.

## Published ports bind to `127.0.0.1`

Every port the stack publishes binds to `STACKR_BIND`, `127.0.0.1` by default, so no service is reachable from another machine unless you choose it ([ADR-0006](../adr/0006-networks-and-published-ports.md)). Services that nothing outside the stack uses (ClickHouse, Valkey, the Collector's own metrics) aren't published at all, and the stack's services reach each other on the `stackr` network by name.

Setting `STACKR_BIND=0.0.0.0` publishes every port on every interface. Before you do, change what is only safe on one machine: put the stack behind a reverse proxy with TLS, and consider which services should be published at all.

### The exception: local Supabase

The Supabase CLI publishes local Supabase's ports (54321 to 54324, and 54327) on every interface, with no setting to bind them to `127.0.0.1` ([ADR-0009](../adr/0009-local-supabase-as-the-database-adapter.md)). Its keys are Supabase's well-known local development keys, and its database password is the fixed `postgres`, so on a machine another computer can reach, anyone who can reach those ports can read and write its database.

On a network you don't trust, either block ports 54320 to 54329 with a firewall, or use the plain PostgreSQL adapter (`STACKR_DATABASE=postgres`), whose port binds to `STACKR_BIND` and whose password is generated.

## Who can do what

| Credential | Can | Who holds it |
|---|---|---|
| `LITELLM_MASTER_KEY` | Administer the gateway: teams, keys, budgets, the admin UI | You; never an application |
| A tenant's key (`make tenant`) | Call models, within its team's budget and rate limits | An application, for that tenant |
| `GRAFANA_ADMIN_PASSWORD` | Everything in Grafana; the data sources and dashboards are read-only in the UI | You |
| `LANGFUSE_ADMIN_PASSWORD` | Langfuse's UI, as the admin of the `stackr` organisation. Sign-up is disabled | You |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | The `stackr` project's API: scores, datasets, traces | The Collector, applications and evaluators |
| Supabase's secret key | Supabase's admin API, including setting a user's tenant | You, and server-side code |
| Supabase's publishable key | Signing users in, and the Data API as the anonymous role | Anyone: it is public |

## What the applications get

The application template carries the same defaults into what it generates ([ADR-0011](../adr/0011-the-application-template-in-detail.md)):

- **Every library surface needs a valid token.** The libraries' REST and WebSocket routes and MCP servers answer 401 without one; only `/healthz` and `/`, which lists the surfaces, don't ask.
- **Users can't choose their tenant.** The tenant comes from `app_metadata.tenant_id`, which only Supabase's service role can set.
- **Tables stay out of `public`.** The libraries' tables live in a schema of the application's own, since Supabase's Data API serves `public` to anyone with the publishable key.
- **Guardrails on every model request,** `pii-mask` and `prompt-injection`, as `LITELLM_GUARDRAILS` configures.
- **Prompts stay off spans** in the gateway's telemetry.

## Usage reports

Where a service reports its usage to its vendor unless told not to, stackr's configuration turns it off: Grafana's analytics, update checks and news feed, Langfuse's telemetry, and Tempo's, Loki's and Pyroscope's usage reports. The gateway uses the model prices bundled with its release instead of fetching them. Local Supabase is configured by its CLI, whose own settings apply.

## Reporting a vulnerability

Please don't open a public issue. Report it privately through GitHub's [private vulnerability reporting](https://github.com/alexnodeland/stackr/security/advisories/new), as the [security policy](../project/security.md) describes. A default that exposes a service beyond the host, a committed secret, or a script that leaks a secret into logs or process listings is a vulnerability in stackr.
