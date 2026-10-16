# Security

stackr's defaults are for local development and single hosts: secrets generated on each machine, and every service reachable from that machine only. This page says what those defaults are, where they end, and what to change before the stack faces a network you don't trust. To report a vulnerability, follow the [security policy](../../project/security.md).

## Secrets live in `.env`

- **Generated, never committed.** `make env` copies `.env.example` to `.env` and replaces each `generate:...` placeholder with a fresh random value: 64 hex characters, 43 URL-safe characters or a UUID, with a prefix where a service expects one (`sk-` for the gateway's master key, `pk-lf-` and `sk-lf-` for Langfuse's keys). `.env` is gitignored and written with mode 0600. `.env.example` holds settings and placeholders only.
- **Stable once made.** Running `make env` again keeps every value already in `.env`, so secrets that encrypt data (`LANGFUSE_SALT`, `LANGFUSE_ENCRYPTION_KEY`, `LITELLM_SALT_KEY`) never change under it. The one value recomputed on every run is `LANGFUSE_OTLP_AUTH`, the Collector's credentials for Langfuse, derived from the project's keys so it always follows them.
- **Required, not empty.** `compose.yaml` refers to each secret as `${NAME:?run make env}`, so Compose refuses to start a service whose secret is missing, rather than starting it with an empty one.
- **Kept off command lines.** Where a secret has to reach a program, it goes through the environment, a file or standard input, never an argument that other processes could read: Valkey writes its password to a config file at start, `db-init`'s script reads the database passwords with `\getenv`, and the smoke test passes keys and passwords to `curl` on standard input.
- **Your own keys.** Provider keys (`ANTHROPIC_API_KEY` and the rest) go in `.env` too, where the gateway reads them. Applications never see them: they call the gateway with a tenant's key.

## Published ports bind to `127.0.0.1`

Every port the stack publishes binds to `STACKR_BIND`, `127.0.0.1` by default, so no service is reachable from another machine unless you choose it ([ADR-0006](../adr/0006-networks-and-published-ports.md)). Services that nothing outside the stack uses (ClickHouse, Valkey, the Collector's own metrics) aren't published at all, and the stack's services reach each other on the `stackr` network by name.

Setting `STACKR_BIND=0.0.0.0` publishes every port on every interface. Don't: to serve users from a machine others can reach, use the [single host](single-host.md) recipe instead.

### On a single host

The host recipe ([RFC-0004](../rfcs/0004-hosting-recipes.md), [ADR-0026](../adr/0026-the-single-host.md)) keeps `STACKR_BIND` at `127.0.0.1` and puts Caddy in front:

- **Only Caddy publishes on a public interface,** on 80 and 443, at `STACKR_EDGE_BIND`, with certificates from Let's Encrypt. It is `127.0.0.1` unless chosen, as `STACKR_BIND` is, so a run of the recipe on a workstation opens nothing; `bootstrap` sets `0.0.0.0` on the host users reach. The overlay removes the ports nothing outside the host needs, and pins Grafana's, Langfuse's, LiteLLM's and MinIO's to `127.0.0.1`, for SSH tunnels, whatever `STACKR_BIND` says. `make smoke` checks both.
- **Docker 28.0 or later.** Before it, machines on the same link could reach ports published on `127.0.0.1`; `bootstrap` refuses an older one.
- **ufw lets in only SSH, HTTP and HTTPS,** SSH on the ports `sshd` listens on. Docker writes its own iptables rules for published ports, which ufw doesn't see, so a port published on every interface would bypass it: that is why nothing but Caddy may bind one.
- **GoTrue's admin API isn't public.** Caddy refuses `/admin/*` at `auth.<domain>`, and on the application's host (`app.<domain>`, where the portal signs in) passes only `/auth/v1/token`, `/auth/v1/user` and `/auth/v1/logout` to GoTrue, answering 404 to anything else under `/auth/v1` and to any path with an `admin` segment; the application's admin commands reach GoTrue on the stack's network, at `AUTH_ADMIN_URL`.
- **No local Supabase,** whose keys are well known: the host runs on the `postgres` adapter, with GoTrue and generated secrets.

### Local Supabase

The Supabase CLI publishes local Supabase's ports (54321 to 54324, and 54327) with no address of their own, so Docker binds them where their network says. `make up` creates that network to publish at `STACKR_BIND`, so they stay on `127.0.0.1` unless you choose otherwise ([ADR-0028](../adr/0028-local-supabase-on-the-loopback.md)), and `make smoke` checks it. That matters: its keys are Supabase's well-known local development keys, and its database password is the fixed `postgres`.

A network made before this, or for another address, is refused: `make down`, then `docker network rm supabase_network_stackr-supabase`, then `make up`.

## Who can do what

| Credential | Can | Who holds it |
|---|---|---|
| `LITELLM_MASTER_KEY` | Administer the gateway: teams, keys, budgets, the admin UI | You; never an application |
| A tenant's key (`make tenant`) | Call models, within its team's budget and rate limits | An application, for that tenant |
| `GRAFANA_ADMIN_PASSWORD` | Everything in Grafana; the data sources and dashboards are read-only in the UI | You |
| `LANGFUSE_ADMIN_PASSWORD` | Langfuse's UI, as the admin of the `stackr` organisation. Sign-up is disabled | You |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | The `stackr` project's API: scores, datasets, traces | The Collector, applications and evaluators |
| `CLICKHOUSE_ADMIN_PASSWORD` | Everything in ClickHouse, the named collections included, from inside its container only ([ADR-0031](../adr/0031-clickhouses-admin-apart-from-langfuse.md)) | You |
| `CLICKHOUSE_PASSWORD` | Langfuse's data in ClickHouse, and the system tables Langfuse reads; nothing else | Langfuse |
| `CLICKHOUSE_BACKUP_PASSWORD` | On a single host, reading and backing up Langfuse's data, the backups' bucket, and the drill's own databases, from inside ClickHouse's container only | `make backup` and the restore drill |
| Supabase's secret key | Supabase's admin API, including setting a user's tenant | You, and server-side code |
| Supabase's publishable key | Signing users in, and the Data API as the anonymous role | Anyone: it is public |

## What the applications get

The application template carries the same defaults into what it generates ([ADR-0011](../adr/0011-the-application-template-in-detail.md)):

- **Every library surface needs a valid token.** The libraries' REST and WebSocket routes and MCP servers answer 401 without one; only `/healthz` and `/`, which lists the surfaces, don't ask.
- **Users can't choose their tenant.** With grantr, the default, a request names its tenant and grantr says whether its user is a member; every command and read is checked against the user's roles, and a key reaches only its own tenant ([ADR-0019](../adr/0019-access-with-grantr-in-the-template.md)). Without it, the tenant comes from `app_metadata.tenant_id`, which only Supabase's service role can set.
- **Tables stay out of `public`.** The libraries' tables live in a schema of the application's own, since Supabase's Data API serves `public` to anyone with the publishable key.
- **Guardrails on every model request,** `pii-mask` and `prompt-injection`, as `LITELLM_GUARDRAILS` configures.
- **Prompts stay off spans** in the gateway's telemetry.

## Usage reports

Where a service reports its usage to its vendor unless told not to, stackr's configuration turns it off: Grafana's analytics, update checks and news feed, Langfuse's telemetry, and Tempo's, Loki's and Pyroscope's usage reports. The gateway uses the model prices bundled with its release instead of fetching them. Local Supabase is configured by its CLI, whose own settings apply.

## Reporting a vulnerability

Please don't open a public issue. Report it privately through GitHub's [private vulnerability reporting](https://github.com/alexnodeland/lattice/security/advisories/new), as the [security policy](../../project/security.md) describes. A default that exposes a service beyond the host, a committed secret, or a script that leaks a secret into logs or process listings is a vulnerability in stackr.
