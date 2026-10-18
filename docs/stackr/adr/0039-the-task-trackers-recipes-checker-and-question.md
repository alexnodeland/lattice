# ADR-0039: The task trackers' recipes, their checker, and the template's question

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland
**Amends:** [lattice RFC-0004](../../rfcs/0004-relayr-and-task-trackers.md)'s "stackr" and "Tenancy, provisioning and credentials", where the departures below say

Builds stackr's half of lattice RFC-0004: the two recipes, the provisioning checklist and `make tracker-check`, and the template's `tracker` question with its example rule. relayr's half, the port, both adapters, the followers, `tracker_router` and the `tracker:` events, is relayr's ([relayr ADR-0033](../../relayr/adr/0033-the-tracker-port-and-runs-that-write-to-it-once.md) to [ADR-0037](../../relayr/adr/0037-what-a-live-plane-settled.md)).

## Context

The RFC has stackr run Plane's Community edition and Vikunja beside the stack, give each tenant a tracker workspace and user by a checklist that a command checks, and let the template wire an application to either. It was written from the trackers' source. Since then a Vikunja v2.7.0 and a Plane v1.4.2 ran live for relayr's contract test ([relayr ADR-0035](../../relayr/adr/0035-what-phase-1-settled-of-the-trackers-unknowns.md), [ADR-0037](../../relayr/adr/0037-what-a-live-plane-settled.md)), and running them, and this checker against them, settled what stackr needed:

- **Plane's API keys see less than the RFC assumed.** `/api/v1/` has no list of a user's workspaces and no webhooks: `GET /api/v1/workspaces/<slug>/webhooks/` is 404 with a working key. It does list a workspace's members with their roles, and a workspace's projects with `is_member`, and it refuses a workspace the key's user isn't in with 403.
- **Vikunja's tokens can't read themselves.** `tokens` is not a scope a token can hold, and `GET /api/v1/tokens` is 401 to one, so a token's expiry can't be read with it. `GET /api/v1/user` needs the `other: user` scope, and a project's webhooks `projects_webhooks: read_all`.
- **Plane's own Compose file doesn't run as it is.** Its `rabbitmq:3.13.x-management-alpine` stops at boot; MinIO's image can no longer be pulled from Docker Hub; its proxy's Caddyfile fails to parse when the certificate settings are set but empty; and a worker started before RabbitMQ takes no task until restarted. Run with its API, worker, web app and proxy, Plane used about 1.7 GiB, 1.25 GiB of it the worker, whose Celery forks a process per CPU, on 16.
- **Plane takes a webhook's URL only if its host has a dot in it:** Django's URL validation refuses `http://app:8000/...` before Plane's own check of private addresses, which `WEBHOOK_ALLOWED_HOSTS` passes by exact name.
- **Vikunja's image runs as uid 1000,** and stops when its files directory is a new volume, which Docker makes root's.

## Decision

### The recipes

- **One directory per tracker, `trackers/plane/` and `trackers/vikunja/`,** each a Compose project of its own (`stackr-plane`, `stackr-vikunja`) with its `NOTICE.md`, read with stackr's `.env`, where `make env` generates their secrets. `make tracker-up TRACKER=…` and `make tracker-down` run them; `scripts/validate` checks both with `docker compose config`.
- **They join the `stackr` network with the services an application talks to,** and keep the rest on their own: Plane's proxy and worker, as `plane-proxy` and `plane-worker`, and Vikunja. Every service's name starts with the tracker's, so none collides on the shared network; Plane's proxy names its upstreams `web`, `api` and `admin`, which are aliases on Plane's own network only.
- **One published port each, at `STACKR_BIND`,** in Compose's long syntax with `host_ip` ([ADR-0006](0006-networks-and-published-ports.md)): Plane's proxy on `PLANE_PORT` (3800), Vikunja on `VIKUNJA_PORT` (3456).
- **Every image is pinned by tag and digest, inline,** so Renovate moves them. Plane's PostgreSQL stays at 15, by a Renovate rule of its own: lattice's rule holds PostgreSQL at 17 for local Supabase, and a major upgrade of Plane's data is Plane's to make.
- **Plane runs ten of its thirteen services, unmodified, at v1.4.2:** its PostgreSQL 15.7, Valkey 7.2, RabbitMQ 4.1.4 in place of the 3.13 that stops, the migrator, the API with one Gunicorn worker, the worker, beat, the web app, the instance's admin (where its first admin is made, and telemetry turned off) and the proxy, with no certificate settings. **Left out:** the public pages, live collaboration, and object storage, so uploads don't work; its address is `plane-uploads.invalid`, so Plane's check of its bucket at startup fails at once rather than asking AWS. The backend's services wait for RabbitMQ and Valkey to be healthy and the migrator to finish. The worker runs its entrypoint's steps with `--concurrency ${PLANE_WORKER_CONCURRENCY:-2}`.
- **Plane allows 300 requests a minute per key** (`PLANE_API_KEY_RATE_LIMIT`), and the template's `TRACKER_BUDGET` is 300 to match, as the RFC says.
- **Plane sends webhooks to one host,** `WEBHOOK_ALLOWED_HOSTS=app.stackr.internal` (`PLANE_WEBHOOK_HOSTS`), never `WEBHOOK_ALLOWED_IPS`, which would open every private address to anyone who can register a webhook. An application generated with `tracker=plane` has that name on the `stackr` network, an alias beside `app`, in its app profile and on a single host. Vikunja's equivalent is `VIKUNJA_OUTGOINGREQUESTS_ALLOWNONROUTABLEIPS=true`, which it has no narrower form of: any Vikunja user can then point a webhook at a private address on the `stackr` network, which is why the guide keeps Vikunja to one tenant, or a few that trust each other.
- **Vikunja runs with sign-up off,** the operator making each tenant's user, and a one-shot service gives uid 1000 its files' volume, with the PostgreSQL image it already pulls.

### The checklist and the checker

- **The checklist is the tracker guide's** ([Task trackers](../guides/trackers.md)): on Plane, the workspace; `relayr-<tenant>`, an ordinary member, since the Community edition makes no bot users; its projects; its key; the webhook, for work items and comments, to `/relayr/v1/trackers/<tenant>/plane`; the credentials. On Vikunja, a script: the user by Vikunja's command line, then its top-level project, its token and the project's webhook through the API.
- **`make tracker-check TENANT=… TRACKER=… APP_ENV=…`** (`scripts/tracker-check`) reads the application's `TRACKER_CREDENTIALS` and `TRACKER_BINDINGS`, and asks the tracker about each step, with the tenant's key and GET requests alone; it changes nothing. A missing step or broken isolation exits 1, and a warning doesn't. It is tested with `httpx.MockTransport` fakes of both trackers and Prometheus (`tests/test_stackr_tracker_check.py`), which also hold that it sends nothing but GETs.
- **Isolation, as far as the API shows it.** On Plane: the user is a member, not an admin, of the tenant's workspace, a member of every bound project and of no other, and refused in every other tenant's workspace that `TRACKER_CREDENTIALS` names. On Vikunja: every bound project is the user's, and it sees no project another user owns.
- **It reads `relayr.trackers.unnudged`** from Prometheus, as `relayr_trackers_unnudged_total{tenant_id=…}` over the last hour, when the `observability` profile runs, and says so when it can't. **The Collector now copies `relayr.tenant.id` to `tenant.id`**, as it copies artifactr's and reflexr's ([ADR-0020](0020-one-tenant-attribute-and-prom-label-proxy.md)), so relayr's metrics carry the `tenant_id` label, and prom-label-proxy scopes them for portalr as it does the libraries'.

### The template

- **A `tracker` question, `none` by default, asked only with the bridge:** `plane` or `vikunja`. The connector writes through relayr's ledger, which is the bridge's. `none` renders exactly as before: five variants, rendered from this change and from its base, are the same.
- **`tracking.py` is one more part, after the bridge,** as `bridge.py` is after the libraries' ([ADR-0021](0021-the-bridge-in-the-template.md)). It holds `Trackers`, over the bridge's ledger and Plane's or Vikunja's adapter on one `httpx` client; `TrackerFollowers`, whose `watch` is composed with the bridge's into reflexr's `on_open` and whose `resume` runs at startup; and `tracker_router`, mounted beside the libraries' routers. It starts after the bridge and stops before it. reflexr accepts `TRACKED` and merges `PUBLISHERS` into its publishers, so only the followers publish `tracker:` events.
- **The settings are `TRACKER_CREDENTIALS`,** a JSON object by tenant as `LITELLM_TENANT_KEYS` is, **`TRACKER_BINDINGS`,** a JSON object from `<tenant>/<workspace>` to a `TrackerBinding`, and `TRACKER_BUDGET`. A binding whose tenant has no credentials stops the application at startup, and an error about the credentials never quotes them.
- **The example, `file-dead-letter`, files each rule's dead letters as one item,** keyed `dead-letter/<rule>`, at high priority with a `run-failed` label, and **comments on it for every dead-lettered run, the first included**, naming the run, its attempts and its error. Its own dead letters are filtered out by its condition, a workspace with no binding files nothing, and an item a person deleted is not filed again.
- **It is checked as everything in the template is.** `check-template` renders seventeen variants, with Plane and grantr, and with Vikunja and no access control. CI's Template job runs both, at 100% coverage: the example's item and comments, its own dead letters, a deleted item, an unbound workspace, a person's change read back, and a webhook refused unsigned and waking the follower when signed, against relayr's `FakeTracker`.

### Departures from the RFC's text

| The RFC | This decision | Why |
|---|---|---|
| The recipe sets `WEBHOOK_ALLOWED_HOSTS` to the application's service name | To `app.stackr.internal`, an alias the application has beside `app` | Plane refuses a URL whose host has no dot |
| Plane is 13 services, 4 to 8 GB | 10 services; about 1.7 GiB was measured with the API, worker, web app and proxy | Storage can't be pulled; the public pages and live collaboration aren't needed for relayr |
| The checker checks each step through the API | Plane's webhook is not checked: the checker says so, and the unnudged count stands in for it | Plane's API keys can't read webhooks |
| `relayr-<tenant>` belongs to exactly one workspace | Checked against every other workspace `TRACKER_CREDENTIALS` names | Plane's API keys list no user's workspaces |
| The checker warns 14 days before a Vikunja token expires | It reads the expiry from the tenant's credentials, `expires_at`, which the provisioning script writes | A token can't read its own expiry |
| relayr registers Vikunja's webhook through the API | The provisioning script registers it, as the tenant's user | relayr has no registration; the script is where the secret is made |
| The example comments on each later failure | It comments on every failure, the first included | One item per rule, one comment per failure, the same each time |
| The credentials are asked again every five minutes | The template's resolver reads `TRACKER_CREDENTIALS` once, at startup: rotating a key restarts the application | It is the environment; a resolver over a secrets store is asked again, as relayr does |

## Options considered

| Option | For | Against |
|---|---|---|
| **Recipes as projects of their own, beside the stack (chosen)** | Opt-in by a command; Plane's ten services stay out of the stack's profiles and its validation | Two more files `make` names, and their own `up` and `down` |
| Recipes as profiles of `compose.yaml` | One project, `make up PROFILES=plane` | Plane's ten services in the stack's reference and checks, for a tracker most deployments won't run |
| **Prefixed service names, with Plane's own names as aliases on its network (chosen)** | Nothing collides on the shared `stackr` network | The proxy's upstreams are aliases, which a reader has to know |
| Plane's own service names | Closest to Plane's file | `api`, `web`, `worker` on a network every application joins |
| **The expiry kept in the credentials (chosen)** | Written by the script that makes the token, beside it | A value the application ignores, in its settings |
| A flag to the checker | Nothing in the settings | Remembered by the operator at every check |

## Consequences

- Easier: an application generated with `tracker` files its rules' dead letters in Plane or Vikunja and reads people's changes back, and a tenant is set up by a checklist that a command checks.
- Wider than the trackers: the Collector's new rule gives every metric, span and log relayr records a `tenant_id`, the bridge's among them, so prom-label-proxy now scopes relayr's series per tenant for portalr, as it scopes the libraries'.
- Harder: Plane's provisioning stays manual, and its webhook can't be checked; a webhook Plane switches off is found only by the unnudged count.
- Checked live, by hand: each recipe started healthy on the loopback, from nothing; a tenant provisioned on each by the guide passed `make tracker-check`, and broke its isolation when it joined a project that wasn't bound; and each tracker delivered a webhook to a stand-in at the application's name, Plane's to `app.stackr.internal`.
- Not done: the Smoke job doesn't run a tracker, so in CI the template's wiring is proved against relayr's fake. The RFC's nightly live run of Plane remains, now that a recipe exists to run it. The unnudged series' name and label are as Prometheus's translation and the Collector's rule make them, not yet seen on a running stack: if either differs, the checker says it couldn't tell, and fails nothing.
- Revisit: Plane's object storage, when a pinned image of an S3 store is chosen for it.
