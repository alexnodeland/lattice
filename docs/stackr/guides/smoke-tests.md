# The smoke tests

`make validate` checks every configuration without starting anything ([Validation and CI](validation.md)). The smoke tests are the other half: they run against a started stack, send telemetry, a gateway request and an application's requests through it, and find each where it should land. CI runs them on every pull request that changes stackr, and you run them after changing a service, an image or a version.

Both are `scripts/smoke`, and need no provider key: the gateway's model replies are mocked.

## `make smoke`

```bash
make up
make smoke
```

`make smoke` checks the profiles in `PROFILES`, the same variable `make up` reads, so check what you started:

```bash
make up PROFILES=observability && make smoke PROFILES=observability
```

It runs one set of checks per profile, and a database check when a profile keeps data in PostgreSQL. Its requests run in the `probe` container, curl on the stack's networks, so they reach each service by name and need no published port: a single host publishes only Caddy's. portalr's readers and `scripts/create-tenant` run on this machine, at Langfuse's and the gateway's ports, which stay on `127.0.0.1` on a single host too. Each check is retried every 3 seconds until it passes or `SMOKE_TIMEOUT` (120 seconds by default) runs out, and every failure is reported before it exits non-zero. A request that stalls is cut off after a quarter of that budget (30 seconds by default), which fails that attempt, not the run, and the check tries again; `make up` waits at most 10 minutes for the stack to be healthy.

### `observability`

It sends a trace, a metric and a log through the Collector's gRPC port with `telemetrygen`, as the service `stackr-smoke` with a run id, and finds:

- the trace in Tempo, by a TraceQL search on the run id
- the metric in Prometheus as `stackr_smoke_total`, which also checks Prometheus's name translation
- the log in Loki
- Tempo's span metrics for the service, and the Collector's own metrics, in Prometheus
- Grafana's four data sources healthy, and the Collector health dashboard provisioned

### The database

Over `db-init`'s own connection to the adapter (its host, admin role and networks, as `make` configures them), it checks that `db-init` created Langfuse's database, the gateway's and GoTrue's, for whichever of those profiles run. With local Supabase, it also checks that Supabase's API answers.

### `langfuse`

It sends a trace with a known id to the Collector's HTTP port, and finds it in Langfuse through the public API, `/api/public/v2/observations`, and in Tempo. That checks the Collector's route to Langfuse, its credentials and Langfuse's ingestion, end to end. It needs `observability` too.

### `gateway`

- The proxy loaded both guardrails, `pii-mask` and `prompt-injection`, and serves both model groups, `default` and `fast`.
- On a new key of the `stackr-smoke` tenant (the team `tenant-stackr-smoke`, the only one allowed mocked replies), a mocked request with a `traceparent` must be routed to `default`, masked by `pii-mask` and priced, and the key's spend must be recorded.
- `prompt-injection` must block an injection attempt with HTTP 400.
- With `observability`, the proxy's spans must continue the caller's trace in Tempo, and with `langfuse`, the trace must be in Langfuse.

The key is deleted at the end.

### `auth`

GoTrue's database exists, and GoTrue serves its ES256 key at `/.well-known/jwks.json`, without the private part. Its admin API refuses a request without the service role's key, and creates a confirmed user with it. The user signs in, at `AUTH_PUBLIC_URL` on a single host, and gets an ES256 token whose issuer is `AUTH_PUBLIC_URL`.

### `edge`: a single host

With `STACKR_RECIPE=host`, `make smoke` adds the edge's checks:

- only Caddy publishes a port on an interface other than the loopback
- Caddy redirects HTTP to HTTPS
- it serves GoTrue at `auth.<domain>`, with a certificate the probe trusts: with `CADDY_TLS="tls internal"`, Caddy's own root, copied from Caddy's container, and nothing else
- it refuses GoTrue's admin API there, with 404
- on the application's host, `/auth/v1/token` signs a user in, and the admin API and the rest of `/auth/v1` are refused in every spelling (the application's checks, below)

### `drill`: a single host's restore drill

After `make backup restore-drill`, `make smoke PROFILES=drill` finds the drill's success in Prometheus, where Grafana's alert reads it.

### `langfuse` and `gateway` together: portalr's readers

portalr's Acceptance job runs neither Langfuse nor LiteLLM, so this reads both through portalr's readers, as the `stackr-smoke` tenant ([portalr ADR-0012](../../portalr/adr/0012-acceptance-against-a-two-tenant-stack.md)). portalr's `scripts/smoke_readers.py` sends Langfuse a trace tagged `tenant:stackr-smoke` with a score on it, and the Langfuse reader must find the score. The LiteLLM reader must read the tenant's team, which the gateway's check created, and find it in every tenant's spend. Each must answer `ok`.

## `make smoke-app`

```bash
make up             # the default profiles, on local Supabase
make smoke-app
```

or, on the `postgres` adapter, with GoTrue:

```bash
make up PROFILES="observability langfuse gateway auth"   # with STACKR_DATABASE=postgres in .env
make smoke-app
```

It runs an application from the template beside the whole stack:

1. It generates an application with both libraries, evals, grantr and relayr's bridge from this checkout, locks its dependencies, and creates a key on the `stackr-smoke` tenant for it.
2. It creates the role the application works as (`db-roles`), starts the application in its app profile, on port `SMOKE_APP_PORT` (8800 by default), with telemetry, Langfuse and mocked model replies, and waits for it to be healthy. On a single host, the application is generated with `hosting: host` and runs with its overlay, behind Caddy, at `https://app.<domain>`.
3. A request without a token must be refused with 401.
4. It creates a user with the identity adapter's admin API, local Supabase's or GoTrue's, and signs them in.
5. With the application's own command, it creates two tenants in grantr: `stackr-smoke`, which the user owns, and `stackr-smoke-other`, which they aren't in. The user's request in the first must succeed, and in the second be refused with 403.
6. As that user, in `stackr-smoke`, it posts a message to the notes agent (artifactr) and opens a ticket for the triage agent (reflexr). Each agent's model request goes through the gateway on the tenant's key.
7. For each agent, the turn or run must end successfully, and its trace must be in Tempo, with the gateway's spans in it, and in Langfuse.
8. The completed turn and the succeeded run must be counted in Prometheus, as `artifactr_turns_total` and `reflexr_runs_total`, for the run's own workspace.
9. PostgreSQL itself must keep each tenant's rows to that tenant, past the libraries' scoping: the application's role sees no rows outside a tenant, and can't write another tenant's.
10. Through relayr's bridge, an `<app>:alert.fired` event must open an incident thread with its timeline, and the user's message in that thread must join the timeline. `<app>` is the application's package name.
11. An `<app>:incident.resolved` event for the same service must post a closing notice in the incident's thread, and propose its postmortem there, drawn from the timeline.
12. The portal: both of portalr's UIs (`/portalr/app/` and `/portalr/admin/`) must answer 200, its `config.json` must name the Supabase project the application was given, the tenant's owner must read the tenant's spend (200), and its usage by workspace, from the gateway, with the portal's own read-only key (`make portal-key`, made for the run and failing it if none is made), that key must be refused chat, the key list and team creation (403), and a tenant the user isn't in must be refused (403). On a single host, the smoke user must also sign in at `https://app.<domain>/auth/v1/token`, and the edge must refuse GoTrue's admin API and the other calls there under a dozen spellings, traversal and escapes among them.
13. Rules from chat: a rule drafted in a thread, by a service principal's key, must go live in reflexr once the user accepts it, and tell the thread of the alert it watches. Before that, a forged `artifactr:proposal_resolved`, published into reflexr, must be refused, and install nothing.

At the end it removes the application, its image and volumes, the key, the user, the portal's key and its `portalr` user, and the application's schema. On the `postgres` adapter it needs the `auth` profile, whose GoTrue signs the user in. Building the application's image fetches the libraries from GitHub at `HEAD`, the commit the application was rendered from, so it needs the network, and `HEAD` must be pushed and the working tree clean: Copier renders uncommitted changes from a commit of its own, which GitHub doesn't have. In CI, `HEAD` is the pull request's merge commit, so the application runs the pull request's libraries.

## In CI

CI's smoke job starts the stack four ways, each on a fresh runner, and runs `make smoke` against it:

| Run | Profiles | Database |
|---|---|---|
| observability | `observability` | None |
| everything on local Supabase, and an application | `observability langfuse gateway`, then `make smoke-app` | Local Supabase |
| everything on PostgreSQL | `observability langfuse gateway` | Plain PostgreSQL |
| a single host, behind Caddy, and an application | `observability langfuse gateway auth`, with `STACKR_RECIPE=host` and Caddy's own CA, then `make smoke-app`, then the backups to a MinIO of the job's own and the restore drill | Plain PostgreSQL |

It installs the Supabase CLI version pinned in `versions.env`, and starts Supabase without the services the smoke tests don't use (`SUPABASE_START_FLAGS`). When a run fails, it prints every container and the last 200 lines of each service's logs, and it always ends with `make reset`.
