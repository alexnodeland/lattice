# The application template

stackr's [Copier](https://copier.readthedocs.io) template generates an application on artifactr, reflexr or both, wired to the stack's ports and nothing else: Supabase for sign-in and PostgreSQL, the gateway for models, the Collector for telemetry, and Langfuse for feedback and experiments ([ADR-0004](../adr/0004-the-application-template.md), [ADR-0011](../adr/0011-the-application-template-in-detail.md), [ADR-0015](../adr/0015-telemetry-mirrors-shutdown-and-namespaces-in-the-template.md), [ADR-0019](../adr/0019-access-with-grantr-in-the-template.md), [ADR-0021](../adr/0021-the-bridge-in-the-template.md), [ADR-0024](../adr/0024-rules-from-chat-in-the-template.md), [ADR-0039](../adr/0039-the-task-trackers-recipes-checker-and-question.md), [ADR-0040](../adr/0040-forms-and-dashboards-in-the-template.md), [ADR-0041](../adr/0041-integrations-switched-per-workspace-in-the-template.md), [ADR-0042](../adr/0042-a-generated-application-as-a-local-product.md)). Its questions are in stackr's `copier.yml`, which the `copier.yml` at lattice's root includes, since Copier reads a repository's root, and its files in `template/`.

## Generate an application

```bash
uvx copier copy gh:alexnodeland/lattice my-app    # or a path to a clone of lattice
cd my-app
git init
make install        # uv sync, which writes uv.lock (commit it), and the git hooks
make env            # .env from .env.example
make check          # lint, types and tests, as its CI runs them
```

- **Which version.** Copier uses the latest tag that is a version. lattice's tags carry their package's name, as in `artifactr-v0.1.0`, so none is, and Copier warns that it found no tags and uses `main`. From a clone, `--vcs-ref HEAD` takes the checkout as it is, uncommitted changes included, which is how stackr's own checks render it.
- **`git init` first.** `make install` installs the git hooks, which need a repository, and stops with a message saying so when there is none; `copier update` later needs one with the generated files committed.
- **No tasks.** The template runs nothing on your machine as it generates, so it needs no `--trust`.

## The questions

| Question | Default | What it decides |
|---|---|---|
| `project_name`, `project_slug`, `description` | My App, `my-app` | The distribution, the package (`my_app`), the OpenTelemetry service and the Compose project |
| `libraries` | `both` | `artifactr`, `reflexr`, or both side by side on one database and one telemetry setup |
| `evals` | Yes | An `evals/` directory with starter evalr experiments |
| `bridge` | Yes | With both libraries: relayr's bridge between them, its incident timeline example, and rules from chat |
| `tracker` | `none` | With the bridge: `plane` or `vikunja`, a task tracker relayr files work in and reads people's changes back from, with its dead-letter example ([Task trackers](trackers.md)); or `none` |
| `ui` | Yes | With artifactr: [artifactr's forms and dashboards](../../artifactr/guides/forms-and-dashboards.md) in the chat (`artifactr-ai[forms]`). The notes agent asks a form with `ask_form` and shows figures with `show_dashboard`; what people send is checked before it commits; with `bridge`, an answer to a form and a submission to one become `ui:form_submitted` for rules ([ADR-0040](../adr/0040-forms-and-dashboards-in-the-template.md)) |
| `native_files` | Yes | With artifactr: [native files](../../artifactr/files/index.md), each read and edited by its app's pinned CLI in a worker of its own with no route out, and, with the portal, edited by people in its browser build. Plumbing only: no app runs until `FILES_CRAFTS` names it ([Native files](#native-files), [ADR-0043](../adr/0043-native-files-in-the-template.md)) |
| `diagrams` | Yes | With `native_files`: [Excalidraw diagrams](../../artifactr/adr/0086-diagrams-data-an-element-scoped-patch-and-its-checks.md) the agent draws from Mermaid or shapes and renders, in a worker of its own with no route out, headless Chromium. Their images are kept in native files' store. Plumbing only: the worker runs with `DIAGRAMS=on`, and diagrams are an integration, `excalidraw`, off in every workspace until switched on. With `bridge`, a diagram's commits reach rules as `excalidraw:elements_changed` ([Diagrams](#diagrams), [ADR-0049](../adr/0049-the-diagrams-worker-excalidraw-in-headless-chromium-behind-a-relay.md)) |
| `access` | `grantr` | `grantr`: tenants, members, roles and keys, and every command and read checked; or `none`: the tenant from the token, and every user of a tenant may do anything in it, including, with `bridge`, installing rules from chat, or `chat:` rules directly through reflexr's REST and MCP, with no review |
| `portal` | Yes | With `access=grantr`: [portalr](../../portalr/index.md)'s app and admin UIs and its router of reads, mounted at `/portalr`, on the same grantr ([ADR-0038](../adr/0038-portalr-in-the-template.md)). It names people by email where the application has the gateway's address and its secret key (`PORTAL_AUTH_URL`, `AUTH_SERVICE_ROLE_KEY`, as invitations need); otherwise the UIs show short ids. (On the PostgreSQL adapter with GoTrue alone, `stackr.env` still defaults `PORTAL_AUTH_URL` to local Supabase's gateway, which isn't there, harmlessly: the UIs show short ids, and invitations fail saying so. They post to Supabase's `/auth/v1/invite` and `/auth/v1/admin/generate_link`, and GoTrue alone serves its API at its root, so they need a gateway in front of it, named in `STACK_PORTAL_AUTH_URL`.) It signs people in through a Supabase project, named in `PORTAL_SUPABASE_URL` and `PORTAL_SUPABASE_KEY` (the publishable key): without them it is off. `PORTAL_SUPABASE_URL=/`, the default, is the application's own origin, which passes the three sign-in calls on to Supabase Auth ([ADR-0042](../adr/0042-a-generated-application-as-a-local-product.md)), and on a single host the application won't start. It adds a Bun build and a network fetch to the image |
| `hosting` | `none` | `none`, or `host`: an overlay, `deploy/host/compose.prod.yaml`, that runs the application's published image behind stackr's edge on a [single host](single-host.md). With the portal, it makes the portal required (the application doesn't start without `PORTAL_SUPABASE_KEY` in `.env`, or with a project that isn't at an https address; the overlay sets the project to `https://app.<STACKR_DOMAIN>`, the application's own address, where the edge answers the three sign-in calls under `/auth/v1` and refuses the rest, so a browser stays on one origin; `STACKR_DOMAIN` goes in `.env` too), trusts the edge's `X-Forwarded-*` headers (`FORWARDED_ALLOW_IPS`), and leaves invitations off, since GoTrue alone has no gateway behind its private address |
| `python_version` | 3.12 | 3.12, 3.13 or 3.14 |
| `app_port` | 8800 | The port the application is published on, on this machine |

The libraries' revisions aren't questions: an application installs them from the commit of lattice it was rendered from ([The libraries' revisions](#the-libraries-revisions)).

Answer non-interactively with `--defaults` and `--data`, as CI does:

```bash
uvx copier copy --defaults --data libraries=reflexr --data evals=false gh:alexnodeland/lattice my-app
```

[Template questions](../reference/template.md) lists every question with its choices, validation and the files each answer generates, and the values derived from them.

## What it generates

| Part | Where | What |
|---|---|---|
| Surfaces | `app.py`, `collaboration.py`, `automation.py` | FastAPI with each library's REST and WebSocket routes and MCP server, under its name: `/artifactr/v1`, `/artifactr/mcp/`, `/reflexr/v1`, `/reflexr/mcp/`. reflexr's reactor runs while the application is up, and stops gracefully when it stops |
| Examples | `notes.py`, `tickets.py` | A `note` artifact type, its agent and a `rating` of turns (artifactr); `ticket.opened` and `ticket.triaged` events, a `triage` rule, its agent, and a `triage-review` of runs (reflexr). reflexr's names are qualified with the application's namespace, its package's name: `my_app:ticket.opened`, `my_app:triage` |
| Identity | `auth.py` | Supabase's access tokens, verified against its published keys (`AUTH_JWKS_URL`), or with a legacy HS256 secret (`AUTH_JWT_SECRET`). The user is `sub`; with `access=none`, the tenant is `app_metadata.tenant_id`. Anything else is 401, the MCP servers included |
| Bridge | `bridge.py`, `incidents.py`, `chat_rules.py` | With `bridge`: relayr's followers, which publish artifactr's events into reflexr from the first request that uses a workspace, and at startup for every workspace the ledger knows and, with grantr, every workspace of every tenant; its outbound adapter, through which rules' runs act in artifactr as their rules' own participants; and the incident timeline example: an `alert.fired` event opens an incident thread with a `timeline` artifact, and people's messages in it are added to the timeline, and an `incident.resolved` event marks the service's latest open incident resolved, with a notice and a proposed `postmortem`, whose outcome relayr scores on the run that proposed it. Rules from chat: the notes agent drafts a rule with relayr's `draft_rule`, and it goes live as a stored rule in reflexr's `chat` namespace once a person who may install rules accepts it; such a rule runs only `notify`, a notice in the thread it names, as its own participant ([ADR-0024](../adr/0024-rules-from-chat-in-the-template.md)); and a rule changed or archived in reflexr directly is proposed back to its artifact, in that thread ([relayr ADR-0030](../../relayr/adr/0030-drift-proposed-back-to-a-rules-artifact.md)) |
| Tracker | `tracking.py` | With `tracker`: relayr's tracker connector. `file-dead-letter` files each rule whose runs are dead-lettered as one item, keyed `dead-letter/<rule>`, and comments on it for each, and never fires on its own dead letters; a follower per bound workspace publishes what people change in its project as `tracker:` events, from when reflexr opens the workspace and from startup; and `POST /relayr/v1/trackers/{tenant}/{tracker}` is where the tracker's webhooks wake it. `TRACKER_CREDENTIALS` holds each tenant's credentials, as `LITELLM_TENANT_KEYS` holds its gateway key, and `TRACKER_BINDINGS` each workspace's project |
| Forms and dashboards | `notes.py`, `collaboration.py`, `bridge.py`, `automation.py` | With `ui`: `artifactr.ui`'s `form`, `submission`, `dashboard` and `app` types beside `note`, its checks on artifactr's `Workspaces`, and its toolset on the notes agent (`ask_form`, `create_form`, `show_dashboard`, `update_dashboard`). With grantr, whoever may restrict what is in a workspace (its admins, and the tenant's owners and admins) may close or change any form in it, as its author may. With `bridge`, relayr's followers publish an answer to a form, and a submission to one, as `ui:form_submitted`, which reflexr accepts from the bridge alone ([ADR-0040](../adr/0040-forms-and-dashboards-in-the-template.md)) |
| Integrations | `access.py`, `app.py` | With `ui` or `tracker`: lattice-core's `Integrations` port, which forms and dashboards (through artifactr's `integration_gate`, `ui_checks` and the agent's `ui_tools`) and the tracker ask before they act in a workspace. With grantr it is `Grants`, which installs what the application ships (`INSTALLED`: the tracker, `ui:forms` and `ui:dashboards`, and `markdown:math` with the portal) and which a tenant's or workspace's admin switches from portalr's admin or `/grantr/v1`: a form in a workspace with forms off is refused as `not_enabled`, and a tracker off there files nothing. Without grantr, each keeps its default ([ADR-0041](../adr/0041-integrations-switched-per-workspace-in-the-template.md)) |
| Native files | `files.py`, `editor.py`, `scripts/craft`, `scripts/crafts/` | With `native_files`: for each app `FILES_CRAFTS` names, a `Worker` at `files-<app>`, `NativeFiles` over them with its stores in the database, `files_router` beside artifactr's at `/artifactr/v1`, the agent's native file tools, and each app's integration, `files:<app>`, installed with grantr and asked on every surface. The image's `files-worker` and `files-editor` targets build each app's from its pinned release ([ADR-0043](../adr/0043-native-files-in-the-template.md)) |
| Diagrams | `files.py`, `collaboration.py`, `scripts/build-diagrams-worker.sh` | With `diagrams`: the `Diagram` type, its checks and its integration, `excalidraw`, on every surface; with `DIAGRAMS=on`, a `WorkerConverter` at `diagrams` and the agent's diagram tools, which keep a conversion's images in native files' store. The image's `diagrams-worker` target builds the worker from the lattice commit `uv.lock` pins artifactr at ([ADR-0049](../adr/0049-the-diagrams-worker-excalidraw-in-headless-chromium-behind-a-relay.md)). With `bridge`, relayr's followers publish a diagram's commits as `excalidraw:elements_changed`, what was added, changed and removed, for rules ([relayr ADR-0041](../../relayr/adr/0041-a-diagrams-commits-bridged-as-its-elements-changed-and-comments-on-them.md)) |
| Portal | `portal.py`, `scripts/build-portal-ui.sh`, `scripts/tailnet.sh`, `brand/` | With `portal`: portalr's router and UIs, off until `PORTAL_SUPABASE_URL` and `PORTAL_SUPABASE_KEY` name the Supabase project the UIs sign in to. On the application's own origin (`/`, the default), it passes Supabase Auth's three sign-in calls, `POST /auth/v1/token`, `GET /auth/v1/user` and `POST /auth/v1/logout`, and nothing else, to `AUTH_ADMIN_URL` or `AUTH_ISSUER`, so the portal signs in wherever the application is reached, with Supabase's gateway or GoTrue alone behind it. With a tracker, it reads what each workspace filed through relayr's tracker reads, which the application mounts. The admin reads Tempo, Loki, Prometheus (through prom-label-proxy), Langfuse and LiteLLM at the addresses `PORTAL_*` and `LANGFUSE_*` name. The image builds the UIs from the commit portalr is pinned at, since a repository install has none ([ADR-0038](../adr/0038-portalr-in-the-template.md)) Mini apps run on `PORTAL_APPS_URL`, an origin of their own that `SandboxOrigin` answers, framed only by `PORTAL_URL`: locally the next port, which `make up` publishes ([portalr ADR-0052](../../portalr/adr/0052-artifacts-inline-in-their-thread.md)). The deployment's brand kit is `PORTAL_BRAND_DIR`: `make brand` starts one in `brand/kit` (`BRAND_FROM=nightshade` or `calm` for an example) and checks it once it's there, and the image carries a copy of `brand/`, so a changed kit needs a new image ([white-labelling the portal](../../portalr/guides/white-labelling.md)) |
| Access | `access.py`, `admin.py`, `access.md` | With `access=grantr`: the tenant the request names (`X-Tenant`, or a WebSocket's `tenant` parameter, or the user's only one), checked against grantr's memberships; service principals' keys in place of tokens; grantr's hook on both libraries' `Workspaces`; grantr's admin API at `/grantr/v1`; `make operator`, `make tenant` and `make migrate-tenants`; and `access.md`, every role against every action, which a test compares with the libraries' catalogs |
| Database | `database.py` | The libraries' SQL storage on `DATABASE_URL`, migrated at startup, in a schema of the application's own (`DATABASE_SCHEMA`) |
| Telemetry | `telemetry.py` | `configure_telemetry` when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, once for both libraries (artifactr's, given reflexr's contribution): FastAPI, SQLAlchemy and httpx traced, the application and its engine included, and the libraries' polling untraced. Langfuse's client when `LANGFUSE_PUBLIC_KEY` is set too, for trace attributes and scores only (`langfuse="scores"`), since traces reach Langfuse through the Collector |
| Gateway | `gateway.py` | Agents on `litellm_model("default")`, each request with its tenant's key and the `pii-mask` and `prompt-injection` guardrails. A mocked reply, for smoke tests, is in the model's settings |
| Feedback | `scores.py` | Each workspace's feedback mirrored to Langfuse scores through evalr's `LangfuseScoreSink`, a score per field by evalr's score mapping, from the first request that uses it, over REST, the WebSocket or MCP. Each mirror saves its cursor, `langfuse`, in the workspace, and carries on after it when the application restarts. The feedback types' score configs are created at startup |
| Evals | `evals/` | The agents on a few examples, judged by evaluators whose verdicts are the application's own feedback types: offline with a scripted model (`make evals`), or in Langfuse with the gateway's model (`make evals-langfuse`). With `bridge`, `incident-scenarios` plays incidents through the application itself, with scripted decisions, to exercise relayr's measures end to end: each postmortem's outcome, how much of it people rewrote, and the time to resolution ([ADR-0030](../adr/0030-the-incident-experiment-and-its-postmortem.md)) |
| Quality gates | `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml` | uv, ruff, pyright in strict mode, pytest with warnings as errors and 100% branch coverage, Conventional Commits. The tests need no network and no stack |
| The `app` profile | `compose.yaml`, `Dockerfile` | The application beside the stack, on its networks |
| Dev container | `.devcontainer/` | Joins the stack's networks when the stack is running |

Every surface is mounted under its library's name in every variant, so a variant, or a later `copier update`, never moves a URL, and both libraries mount side by side without clashing.

### Settings

The application reads the stack's ports from its environment ([`settings.py`](https://github.com/alexnodeland/lattice/blob/main/packages/stackr/template/src/%7B%7B%20package_name%20%7D%7D/settings.py.jinja)); `.env.example` has every setting, with the stack's addresses on this machine:

| Port | Settings |
|---|---|
| Telemetry | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_METRIC_EXPORT_INTERVAL` |
| Database | `DATABASE_URL`, `DATABASE_SCHEMA`, `DATABASE_ADMIN_URL` for row-level security |
| Identity | `AUTH_JWKS_URL`, `AUTH_ISSUER`, `AUTH_AUDIENCE`, `AUTH_JWT_SECRET`; `AUTH_SERVICE_ROLE_KEY` with grantr, for its commands to find users by email, at `AUTH_ADMIN_URL` when the admin API isn't at the issuer; `AUTH_TENANT_CLAIM` without |
| LLM gateway | `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `LITELLM_TENANT_KEYS`, `LITELLM_MODEL`, `LITELLM_GUARDRAILS` |
| Evaluation data | `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` |

The stack's two other ports, profiles and object storage, aren't read: nothing in a generated application profiles or stores objects yet. An application that adds them reads `PYROSCOPE_SERVER_ADDRESS` with a Pyroscope SDK, and the `S3_*` settings with an S3 client, with a bucket of its own ([ADR-0005](../adr/0005-ports-and-adapters-for-the-stack.md)).

Fill in two things after `make env`: `LITELLM_API_KEY`, a tenant's key from `make tenant NAME=acme` in stackr (or `LITELLM_TENANT_KEYS`, a JSON object of a key per tenant), and `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`, from stackr's `.env`. Without a Langfuse public key, Langfuse is off; without `OTEL_EXPORTER_OTLP_ENDPOINT`, telemetry is off; without `DATABASE_URL`, workspaces live in memory.

## Running it

| Command | Runs the application |
|---|---|
| `make serve` | On this machine, with the settings in `.env`, at `APP_HOST:APP_PORT` |
| `make up` | In the `app` profile: builds its image and runs it beside the stack, at <http://localhost:8800> (`app_port`) |
| `make down`, `make logs` | Stops the app profile, or follows its logs |
| `make tailnet`, `make tailnet-off` | With the portal: serves the application on this machine's tailnet name over HTTPS with `tailscale serve`, for your tailnet only, and prints its address; or stops. See [On your tailnet](#on-your-tailnet) |

A WebSocket carries its token in the `access_token` query parameter, so the application keeps it out of what it records: uvicorn's access log and its log of WebSockets, through `redaction.py`, and the spans' URLs, through the libraries' `instrument_app` ([artifactr ADR-0068](../../artifactr/adr/0068-an-access-token-redacted-from-span-urls.md)).

With `access=grantr`, the application's own commands set up its tenants, in process, on its database ([grantr ADR-0021](../../grantr/adr/0021-the-deployments-own-tools.md)). Each takes a user's email, which Supabase Auth's admin API looks up with `AUTH_SERVICE_ROLE_KEY`, or their id:

| Command | What it does |
|---|---|
| `make first-run EMAIL=...` | The first person in: makes their account in Supabase Auth if they have none, with a password it asks for twice; makes them the deployment's operator if it has none; creates a tenant they own (`TENANT`, `home`); and gives them a workspace there to administer (`WORKSPACE`, `main`) if they can't open it, which the app then lists. Each step is skipped once done, and `EMAIL` may be an existing user's id |
| `make operator EMAIL=...` | Makes a user the deployment's first operator, who may create tenants through grantr's API |
| `make tenant NAME=... OWNER=...` | Creates a tenant, with its owner, once |
| `make migrate-tenants` | Moves each user's tenant from their token's `app_metadata.tenant_id` into grantr: a new tenant's earliest user becomes its owner, and the rest its admins; a tenant grantr holds gains its claimed users who aren't members, as admins. It prints who got what, and can run again |
| `make access-matrix` | Rewrites `access.md`, every role against every action, to review and commit |

`make tenant` here is grantr's; stackr's own `make tenant` creates a tenant's team and key on the gateway.

The **app profile** is the application's own `compose.yaml`, not a service in stackr's. Its service joins the `stackr` network and local Supabase's, and reads [`stackr.env`](https://github.com/alexnodeland/lattice/blob/main/packages/stackr/template/stackr.env) after `.env`, which replaces the stack's addresses in `.env` with their names on those networks. Its `DATABASE_URL` is local Supabase's PostgreSQL by name, unless `STACK_DATABASE_URL` in `.env` names another database, and its commands find people through local Supabase's gateway, unless `STACK_AUTH_ADMIN_URL` names another. Compose sets `PORTAL_UI_DIR` to the image's UIs, whatever `.env` says.

So start the stack first: stackr's default `make up`, with local Supabase, or the PostgreSQL adapter (below). The image is built in two stages, the first with git to fetch the libraries at their pinned commits, so building it needs the network.

### From `make up` to a portal with chat

With grantr and the portal, a person signs in to the app and chats with its agent through the gateway after these steps, on either of stackr's database adapters:

1. In stackr: `make up`, then `make tenant NAME=home`, which prints a gateway key for the tenant's team.
2. In the application: `make install` and `make env`, then fill in `.env` (`scripts/wire-app <app>` in stackr writes all but the gateway keys from stackr's `.env`, with `--analytics`, `--umami` and `--langfuse-project` as you run them): `LITELLM_API_KEY`, the key from step 1; `AUTH_SERVICE_ROLE_KEY`; `PORTAL_SUPABASE_KEY`; and, for Langfuse, its keys and `PORTAL_LANGFUSE_PROJECT`. On local Supabase the two keys are `supabase status`'s secret and publishable keys. On the PostgreSQL adapter, GoTrue alone, `AUTH_SERVICE_ROLE_KEY` is stackr's own (its `.env`), `PORTAL_SUPABASE_KEY` any name such as `sb_publishable_local`, since GoTrue asks for none, and these lines, in place of `.env.example`'s (the local commands read a setting's first line, Compose its last), point the application at GoTrue (`AUTH_ISSUER` is stackr's `AUTH_PUBLIC_URL`) and the stack's PostgreSQL:

   ```bash
   AUTH_ISSUER=http://localhost:9999
   AUTH_JWKS_URL=http://localhost:9999/.well-known/jwks.json
   DATABASE_URL=postgresql+asyncpg://postgres:<POSTGRES_ADMIN_PASSWORD>@127.0.0.1:<POSTGRES_PORT>/postgres
   STACK_AUTH_JWKS_URL=http://gotrue:9999/.well-known/jwks.json
   STACK_AUTH_ADMIN_URL=http://gotrue:9999
   STACK_DATABASE_URL=postgresql+asyncpg://postgres:<POSTGRES_ADMIN_PASSWORD>@postgres:5432/postgres
   ```

3. `make up`, then `make first-run EMAIL=you@example.com`, which asks for your password.
4. Sign in at <http://localhost:8800/portalr/app/>, open `home`'s `main`, and start a thread. The agent asks the gateway's `default` model group with the tenant's key, and its trace reaches Tempo and Langfuse through the Collector.

The portal signs in on the application's own origin (`PORTAL_SUPABASE_URL=/`), so none of this changes on a tailnet. `make portal-key` in stackr, for `PORTAL_LITELLM_KEY`, adds spend to admin.

### On your tailnet

`make tailnet` serves the application on this machine's tailnet name, over HTTPS, for your tailnet only, with `tailscale serve`, and prints the address, `https://<machine>.<tailnet>.ts.net/portalr/app/`. It never uses `tailscale funnel`, which would put it on the internet, and every port stays on `127.0.0.1`, where Tailscale reaches it ([ADR-0042](../adr/0042-a-generated-application-as-a-local-product.md)).

- **It needs Tailscale,** signed in, on this machine and the device. It finds the CLI on the `PATH` or in the macOS app (`/Applications/Tailscale.app`), or where `TAILSCALE` says, and installs nothing.
- **It uses one HTTPS port,** `TAILNET_PORT`, 443 by default. It refuses a port something else is served on, or one Funnel puts on the internet, so it never replaces another server's and never leaves the application public: choose another, such as `make tailnet TAILNET_PORT=8444`. `make tailnet-off` with the same port removes what it set up there, and nothing else. `tailscale serve --bg` keeps the setting across restarts until then.
- **Nothing in `.env` changes.** The browser reaches only the application's origin: its UIs, its API and WebSockets, and the three sign-in calls it passes on. The content security policy's `connect-src` is `'self'`, with no CORS and no cookies (the session is in the browser's storage, per origin, so a device signs in once on the tailnet's address).
- **Email links** (invitations, recoveries) point where Supabase Auth's site URL says, which is stackr's setting, not the application's: `AUTH_SITE_URL` on the PostgreSQL adapter, which is `http://localhost:8800` until you set it to the tailnet's address. The application passes no `redirect_to`, so GoTrue's allow-list of redirects has nothing to allow; the portal has no page to set a password from one yet, so people are made with `make first-run` or the admin API.
- **Native files' editors** each run on an origin of their own, so each takes a tailnet port of its own: see [Native files](#native-files).

**Stopping:** the server lets open requests finish for `DRAIN`. Then each library's MCP server stops, then its work, then its feedback mirrors, and the database closes last ([ADR-0015](../adr/0015-telemetry-mirrors-shutdown-and-namespaces-in-the-template.md)). reflexr's reactor gives running actions `STOP_GRACE` to end, and records those it then cancels as abandoned attempts, which the next start retries ([reflexr's graceful stop](../../reflexr/guides/reactor.md#running-the-reactor)). artifactr's runner stops the agent's turns still going, each recording that it stopped ([artifactr's serving guide](../../artifactr/guides/serving.md#adding-the-router)). Together, and with the rest of the shutdown, they must end within the app profile's `stop_grace_period`.

The **dev container** is built on `.devcontainer/compose.yaml`. When the stack is running, its `initialize.sh` adds the stack's networks and `stackr.env`'s addresses, so the application inside it reaches the stack by name; otherwise the dev container runs on its own.

### Native files

With `native_files`, `make env` generates each worker's own token, `FILES_<APP>_TOKEN`, in a `.env` only its owner may read (it needs `openssl`), and `FILES_CRAFTS` names the apps whose workers run, in `.env` or for one run:

```bash
make up FILES="wordcraft gridcraft pdfcraft"
```

Each app is a Compose profile, `files-<app>`, which `make up` adds, and its first build fetches its release from GitHub, checks it against the pin in `scripts/crafts/`, and unpacks it into the image. `make down` stops every worker. It needs Compose 2.20 or later, for the application's `depends_on` with `required: false`, and a Docker Engine whose bridge driver honours `inhibit_ipv4`, which gives the host no address on a worker's network (`scripts/check-files` prints the Engine it proved it on). Native files' routes and the agent's tools are there while any app runs, and each running app is installed as an integration, `files:<app>`, switched per workspace like any other: WordCraft, once `FILES_CRAFTS` names it, is on in every workspace of every tenant until an admin switches it off, and the others are off until an admin switches them on.

- **The workers have no route out.** Each runs read-only, as a user that isn't root, with no capabilities, under an init, with limits on its memory and swap, CPUs and processes (`FILES_WORKER_MEMORY`, `FILES_WORKER_CPUS`, `FILES_WORKER_TMPFS`), and alone on a network of its own, `files-<app>`, which is internal: only the application, which joins each, reaches it, by its name, and no port is published. Each call's own limits are artifactr's (`FILES_WORKER_LIMITS`); after each call the worker kills whatever its user left running and empties `/tmp`. `make serve` can't reach them, so it runs native files off.
- **People's uploads and check-ins are held back** as artifactr's defaults do, unless `.env` says otherwise (native files ADR-0017): `FILES_UPLOADS_PER_MINUTE` (20 starts a person a minute), `FILES_UPLOADS_AT_ONCE` (8 files read at once, each held in memory), `FILES_UPLOADS_PER_TENANT` (half of those, unset) and `FILES_UPLOADS_EACH` (2) shares of them, and `FILES_READINGS` (2 of a tenant's files its apps read at once). `FILES_WORKSPACE_QUOTA` and `FILES_TENANT_QUOTA`, `<bytes>` or `<bytes>,<files>`, hold each workspace's and tenant's files to a quota; empty, none.
- **The editors are origins of their own.** With the portal, GridCraft's, PdfCraft's and CADCraft's browser builds are served as released, each on its own port of this machine's loopback, `app_port` and two, three and four (`GRIDCRAFT_EDITOR_PORT`, `PDFCRAFT_EDITOR_PORT`, `CADCRAFT_EDITOR_PORT`), with lattice's shim, which only `PORTAL_URL` may frame, and the portal's `config.json` names them (`Site.editors`) for its check-out.
- **Elsewhere, name each editor.** `APP_BIND` publishes the editors where it publishes the application, so a LAN is opt-in, and puts them before anyone on that network. `PORTAL_URL` must be the portal's origin exactly: `http://localhost:8800` is not `http://127.0.0.1:8800`, and a shim told one refuses the other. On a tailnet, serve each editor on a port of its own, since an origin is a host and a port, and tell the application where they are, and where the portal is:

  ```bash
  tailscale serve --bg --https=8802 http://127.0.0.1:8802
  ```

  ```dotenv
  PORTAL_URL=https://my-machine.my-tailnet.ts.net
  FILES_EDITORS={"files:gridcraft": "https://my-machine.my-tailnet.ts.net:8802/"}
  ```

- **No upload route yet.** Nothing in lattice makes a native file from an upload over HTTP: files arrive through `NativeFiles.upload` in code, and people check them out and in from the portal ([ADR-0043](../adr/0043-native-files-in-the-template.md)).

`scripts/check-files` in stackr builds the workers and editors as a generated application does, and checks their posture, value by value, that they reach nothing outside their networks, that nothing outlives a call, and that hostile files are refused in time.

### Diagrams

With `diagrams`, `make env` generates the diagrams worker's own token, `DIAGRAMS_TOKEN`, and `DIAGRAMS=on` starts the worker, in `.env` or for one run:

```bash
make up DIAGRAMS=on
```

The worker is a Compose profile, `diagrams`, which `make up` adds; its first build clones lattice at the commit `uv.lock` pins artifactr at, builds the worker's page and server with Bun, and installs Noto CJK into Playwright's image ([ADR-0049](../adr/0049-the-diagrams-worker-excalidraw-in-headless-chromium-behind-a-relay.md)). The image is about 1 GB. With the worker running, the agent has `read_diagram`, `draw_mermaid`, `draw` and `edit_elements` in every workspace where diagrams are on: they are an integration, `excalidraw`, off until an admin switches it on. Its drawings are proposals, as any agent's change is.

- **The worker has no route out**, as a native file's worker hasn't: read-only, as a user that isn't root, with no capabilities, under an init, with 1 GiB of memory and no swap (`DIAGRAMS_MEMORY`), one CPU (`DIAGRAMS_CPUS`), and alone on its own internal network, `diagrams`, with its relay, `diagrams`, which the application reaches on `files`. Its page loads nothing but its own files, and its exports name no address outside them.
- **One job at a time, each within 10 seconds.** A job past its deadline is answered `timeout`, and the page it ran on is thrown away.
- **CJK is drawn in Noto CJK**, not Excalidraw's Xiaolai, until Xiaolai's author answers whether Excalidraw's modified copy may keep its reserved name (lattice#679); then `DIAGRAMS_XIAOLAI=1` builds the worker with it. Its SVGs embed the Latin faces they use and leave CJK to the viewer's own.
- **The worker comes from the libraries' commit.** Its build clones lattice at the commit `uv.lock` pins artifactr at, so a lock that predates the worker can't build it: `uv lock --upgrade-package artifactr-ai` moves it on. The build also checks that the worker drives the Playwright whose Chromium the image holds, and says to run `copier update` if the template and the libraries have drifted apart.

`scripts/check-files` in stackr builds the worker as a generated application does, checks its posture value by value, that it reaches nothing outside its network, the application's side of its relay and the application's name included, and that it draws, renders and refuses as artifactr's converter expects.

## Keeping it up to date

### The template: `copier update`

```bash
uvx copier update
```

pulls in the template's improvements since the application was generated, keeping your own changes. An application generated before the portal existed is asked the `portal` question when it updates, and the default is yes: say no to keep the image as it is, since the portal adds a Bun stage to the build and a network fetch of lattice at the pinned commit. One generated before the forms is asked the `ui` question, also yes by default, which adds artifactr's `forms` extra, the types and checks, and four tools to the notes agent. It asks the questions again, with your previous answers (recorded in `.copier-answers.yml`) as the defaults; `--skip-answered` asks only the new ones. It needs a git repository with no uncommitted changes, and marks conflicts between the template's changes and yours inline, for you to resolve. Review the result like any other change, and run `make check`.

An application updated to [ADR-0042](../adr/0042-a-generated-application-as-a-local-product.md) keeps its `.env`, which `copier update` never touches: set `PORTAL_SUPABASE_URL=/` there for the portal to sign in on its own origin, as `.env.example` now does.

Updating also changes something for every application, with the portal or without it: `LOG_CONFIG` puts `grantr.audit` and `portalr.access` at INFO, so grantr's audit entries, which the root's WARNING dropped, now reach Loki through the Collector ([portalr ADR-0035](../../portalr/adr/0035-tools-and-the-record-of-opening-them.md)).

### The portal's Bun

The portal's image stage builds portalr's UIs with Bun, pinned in the `Dockerfile` by tag and digest (`FROM oven/bun:<tag>@sha256:<digest>`), as lattice itself pins Bun in its `.prototools`; `check-template` holds the two to the same version. The generated application is outside lattice's Renovate, so a new Bun comes with `copier update`, or by changing the tag and the digest together (`docker buildx imagetools inspect oven/bun:<tag>`). The UIs' commit is not pinned a second time: `scripts/build-portal-ui.sh` reads it from `uv.lock`, where portalr's git source says which commit is installed.

### The libraries' revisions

artifactr, reflexr and evalr come from lattice, at the commit of lattice the template was rendered from, in `pyproject.toml`'s `[tool.uv.sources]` ([ADR-0018](../adr/0018-the-template-pins-the-libraries-at-its-own-commit.md)):

```toml
[tool.uv.sources]
artifactr-ai = { git = "https://github.com/alexnodeland/lattice", subdirectory = "packages/artifactr", rev = "<the rendered commit>" }
reflexr = { git = "https://github.com/alexnodeland/lattice", subdirectory = "packages/reflexr", rev = "<the rendered commit>" }
evalr = { git = "https://github.com/alexnodeland/lattice", subdirectory = "packages/evalr", rev = "<the rendered commit>" }
```

Each library's own `evalr = { workspace = true }` becomes the same repository and commit, so evalr is one package at one commit. An application without evals has no evalr line, and gets evalr through the libraries.

`copier update` moves the template's code and the libraries together, to a combination lattice's CI checked together. To try another commit, change every `rev` to it, then `uv lock && make check`; the libraries must come from one commit, or `uv lock` fails, naming both. `copier update` keeps the edit, and marks a conflict when it moves the lines.

lattice's tags carry their package's name, so Copier records the application's `_commit` as `git describe --tags` of the nearest one, such as `evalr-v0.2.0-1-gf4e1841`. Updates read it correctly. An application rendered from a pull request's branch stays installable after a squash merge, since GitHub keeps the pull request's commits.

## How the template is checked

- **`make validate`** renders every variant (three choices of libraries, with and without evals, with grantr or without access control, both libraries without the bridge, both with grantr and without the portal, both without the forms, both without native files, both without diagrams, on a single host, and both with each tracker) with `scripts/check-template`, under a name whose slug is the longest Copier accepts and whose package sorts before `conftest`, and checks that nothing is left unrendered, that the libraries come from lattice at the commit it was rendered from, that the Python passes the generated project's own ruff settings, and that the YAML, shell scripts and Compose file pass their linters.
- **CI's template job** generates each variant with grantr, the largest again on Python 3.14, again without access control, again without the portal, again without the forms, again with Plane, and without access control with Vikunja, and runs its own `make check`: lint, strict types, and the tests with 100% coverage. `scripts/check-app` sets `libraries_path`, so the application installs the libraries from the checkout, and the job runs when stackr or any library changes. A library's change and the template's then land in one pull request, checked together.
- **`stackr:access-matrix`** checks that the template's `access.md`, which it renders for each choice of libraries, matches the libraries' catalogs and grantr's roles; `scripts/access-matrix` rewrites it.
- **`make smoke-app`** generates an application with both libraries, evals and the bridge, which installs the libraries from GitHub at `HEAD`, as an application generated from lattice does (so `HEAD` must be pushed and the working tree clean; in CI, it is the pull request's merge commit). It runs it in its app profile beside the whole stack, with its portal (it serves both UIs, and asks grantr before a read), creates two tenants with its own command, signs a user in to the one they own, through the application's own origin on the local recipes, and has them refused the other, traces its agents through the gateway into Tempo and Langfuse, and plays an incident through the bridge, from its alert to its proposed postmortem, and a rule from chat, from its draft to its notice ([The smoke tests](smoke-tests.md)).

To render and check one variant locally, from lattice's root, whose `copier.yml` points Copier at the template, with the libraries from the checkout:

```bash
uv run copier copy --defaults --vcs-ref HEAD --data libraries=both --data libraries_path="$PWD/packages" . /tmp/my-app
cd /tmp/my-app && git init && make install && make check
```
