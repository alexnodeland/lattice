# The smoke tests

`make validate` checks every configuration without starting anything ([Validation and CI](validation.md)). The smoke tests are the other half: they run against a started stack, send telemetry, a gateway request and an application's requests through it, and find each where it should land. CI runs them on every pull request, and you run them after changing a service, an image or a version.

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

It runs one set of checks per profile, and a database check when a profile keeps data in PostgreSQL. Each check is retried every 3 seconds until it passes or `SMOKE_TIMEOUT` (120 seconds by default) runs out, and every failure is reported before it exits non-zero.

### `observability`

It sends a trace, a metric and a log through the Collector's gRPC port with `telemetrygen`, as the service `stackr-smoke` with a run id, and finds:

- the trace in Tempo, by a TraceQL search on the run id
- the metric in Prometheus as `stackr_smoke_total`, which also checks Prometheus's name translation
- the log in Loki
- Tempo's span metrics for the service, and the Collector's own metrics, in Prometheus
- Grafana's four data sources healthy, and the Collector health dashboard provisioned

### The database

Over `db-init`'s own connection to the adapter (its host, admin role and networks, as `make` configures them), it checks that `db-init` created Langfuse's database and the gateway's, for whichever of those profiles run. With local Supabase, it also checks that Supabase's API answers.

### `langfuse`

It sends a trace with a known id to the Collector's HTTP port, and finds it in Langfuse through the public API, `/api/public/v2/observations`, and in Tempo. That checks the Collector's route to Langfuse, its credentials and Langfuse's ingestion, end to end. It needs `observability` too.

### `gateway`

- The proxy loaded both guardrails, `pii-mask` and `prompt-injection`, and serves both model groups, `default` and `fast`.
- On a new key of the `stackr-smoke` tenant (the team `tenant-stackr-smoke`, the only one allowed mocked replies), a mocked request with a `traceparent` must be routed to `default`, masked by `pii-mask` and priced, and the key's spend must be recorded.
- `prompt-injection` must block an injection attempt with HTTP 400.
- With `observability`, the proxy's spans must continue the caller's trace in Tempo, and with `langfuse`, the trace must be in Langfuse.

The key is deleted at the end.

## `make smoke-app`

```bash
make up             # the default profiles, on local Supabase
make smoke-app
```

It runs an application from the template beside the whole stack:

1. It generates an application with both libraries and evals from this checkout, locks its dependencies, and creates a key on the `stackr-smoke` tenant for it.
2. It starts the application in its app profile, on port `SMOKE_APP_PORT` (8800 by default), with telemetry, Langfuse and mocked model replies, and waits for it to be healthy.
3. A request without a token must be refused with 401.
4. It creates a user of the tenant `stackr-smoke` with local Supabase's admin API, and signs them in.
5. As that user, it posts a message to the notes agent (artifactr) and opens a ticket for the triage agent (reflexr). Each agent's model request goes through the gateway on the tenant's key.
6. For each agent, the turn or run must end successfully, and its trace must be in Tempo, with the gateway's spans in it, and in Langfuse.
7. The completed turn and the succeeded run must be counted in Prometheus, as `artifactr_turns_total` and `reflexr_runs_total`, for the run's own workspace.

At the end it removes the application, its image and volumes, the key, the user and the application's schema. It needs local Supabase, whose Auth signs the user in, so it fails on the `postgres` adapter. Building the application's image fetches the libraries from GitHub, so it needs the network.

## In CI

CI's smoke job starts the stack three ways, each on a fresh runner, and runs `make smoke` against it:

| Run | Profiles | Database |
|---|---|---|
| observability | `observability` | None |
| everything on local Supabase, and an application | `observability langfuse gateway`, then `make smoke-app` | Local Supabase |
| everything on PostgreSQL | `observability langfuse gateway` | Plain PostgreSQL |

It installs the Supabase CLI version pinned in `versions.env`, and starts Supabase without the services the smoke tests don't use (`SUPABASE_START_FLAGS`). When a run fails, it prints every container and the last 200 lines of each service's logs, and it always ends with `make reset`.
