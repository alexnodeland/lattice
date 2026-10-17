# The application template

stackr's [Copier](https://copier.readthedocs.io) template generates an application on artifactr, reflexr or both, wired to the stack's ports and nothing else: Supabase for sign-in and PostgreSQL, the gateway for models, the Collector for telemetry, and Langfuse for feedback and experiments ([ADR-0004](../adr/0004-the-application-template.md), [ADR-0011](../adr/0011-the-application-template-in-detail.md), [ADR-0015](../adr/0015-telemetry-mirrors-shutdown-and-namespaces-in-the-template.md), [ADR-0019](../adr/0019-access-with-grantr-in-the-template.md), [ADR-0021](../adr/0021-the-bridge-in-the-template.md), [ADR-0024](../adr/0024-rules-from-chat-in-the-template.md), [ADR-0039](../adr/0039-forms-and-dashboards-in-the-template.md)). Its questions are in stackr's `copier.yml`, which the `copier.yml` at lattice's root includes, since Copier reads a repository's root, and its files in `template/`.

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
| `ui` | Yes | With artifactr: [artifactr's forms and dashboards](../../artifactr/guides/forms-and-dashboards.md) in the chat (`artifactr-ai[forms]`). The notes agent asks a form with `ask_form` and shows figures with `show_dashboard`; what people send is checked before it commits; with `bridge`, an answer to a form and a submission to one become `ui:form_submitted` for rules ([ADR-0039](../adr/0039-forms-and-dashboards-in-the-template.md)) |
| `access` | `grantr` | `grantr`: tenants, members, roles and keys, and every command and read checked; or `none`: the tenant from the token, and every user of a tenant may do anything in it, including, with `bridge`, installing rules from chat, or `chat:` rules directly through reflexr's REST and MCP, with no review |
| `portal` | Yes | With `access=grantr`: [portalr](../../portalr/index.md)'s app and admin UIs and its router of reads, mounted at `/portalr`, on the same grantr ([ADR-0038](../adr/0038-portalr-in-the-template.md)). It names people by email where the application has the gateway's address and its secret key (`PORTAL_AUTH_URL`, `AUTH_SERVICE_ROLE_KEY`, as invitations need); otherwise the UIs show short ids. (On the PostgreSQL adapter with GoTrue alone, `stackr.env` still defaults `PORTAL_AUTH_URL` to local Supabase's gateway, which isn't there: people and invitations are enabled but unreachable, harmlessly, and the UIs show short ids until `STACK_PORTAL_AUTH_URL` names a gateway.) It signs people in through a Supabase project, named in `PORTAL_SUPABASE_URL` and `PORTAL_SUPABASE_KEY` (the publishable key): without them it is off, and on a single host the application won't start. It adds a Bun build and a network fetch to the image |
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
| Forms and dashboards | `notes.py`, `collaboration.py`, `bridge.py`, `automation.py` | With `ui`: `artifactr.ui`'s `form`, `submission`, `dashboard` and `app` types beside `note`, its checks on artifactr's `Workspaces`, and its toolset on the notes agent (`ask_form`, `create_form`, `show_dashboard`, `update_dashboard`). With grantr, whoever may restrict what is in a workspace (its admins, and the tenant's owners and admins) may close or change any form in it, as its author may. With `bridge`, relayr's followers publish an answer to a form, and a submission to one, as `ui:form_submitted`, which reflexr accepts from the bridge alone ([ADR-0039](../adr/0039-forms-and-dashboards-in-the-template.md)) |
| Portal | `portal.py`, `scripts/build-portal-ui.sh` | With `portal`: portalr's router and UIs, off until `PORTAL_SUPABASE_URL` and `PORTAL_SUPABASE_KEY` name the Supabase project the UIs sign in to. The admin reads Tempo, Loki, Prometheus (through prom-label-proxy), Langfuse and LiteLLM at the addresses `PORTAL_*` and `LANGFUSE_*` name. The image builds the UIs from the commit portalr is pinned at, since a repository install has none ([ADR-0038](../adr/0038-portalr-in-the-template.md)) |
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

A WebSocket carries its token in the `access_token` query parameter, so the application keeps it out of what it records: uvicorn's access log and its log of WebSockets, through `redaction.py`, and the spans' URLs, through the libraries' `instrument_app` ([artifactr ADR-0068](../../artifactr/adr/0068-an-access-token-redacted-from-span-urls.md)).

With `access=grantr`, the application's own commands set up its tenants, in process, on its database ([grantr ADR-0021](../../grantr/adr/0021-the-deployments-own-tools.md)). Each takes a user's email, which Supabase Auth's admin API looks up with `AUTH_SERVICE_ROLE_KEY`, or their id:

| Command | What it does |
|---|---|
| `make operator EMAIL=...` | Makes a user the deployment's first operator, who may create tenants through grantr's API |
| `make tenant NAME=... OWNER=...` | Creates a tenant, with its owner, once |
| `make migrate-tenants` | Moves each user's tenant from their token's `app_metadata.tenant_id` into grantr: a new tenant's earliest user becomes its owner, and the rest its admins; a tenant grantr holds gains its claimed users who aren't members, as admins. It prints who got what, and can run again |
| `make access-matrix` | Rewrites `access.md`, every role against every action, to review and commit |

`make tenant` here is grantr's; stackr's own `make tenant` creates a tenant's team and key on the gateway.

The **app profile** is the application's own `compose.yaml`, not a service in stackr's. Its service joins the `stackr` network and local Supabase's, and reads [`stackr.env`](https://github.com/alexnodeland/lattice/blob/main/packages/stackr/template/stackr.env) after `.env`, which replaces the stack's addresses in `.env` with their names on those networks. Its `DATABASE_URL` is local Supabase's PostgreSQL by name, unless `STACK_DATABASE_URL` in `.env` names another database.

So start the stack first, with local Supabase: stackr's default `make up`. The image is built in two stages, the first with git to fetch the libraries at their pinned commits, so building it needs the network.

**Stopping:** the server lets open requests finish for `DRAIN`. Then each library's MCP server stops, then its work, then its feedback mirrors, and the database closes last ([ADR-0015](../adr/0015-telemetry-mirrors-shutdown-and-namespaces-in-the-template.md)). reflexr's reactor gives running actions `STOP_GRACE` to end, and records those it then cancels as abandoned attempts, which the next start retries ([reflexr's graceful stop](../../reflexr/guides/reactor.md#running-the-reactor)). artifactr's runner stops the agent's turns still going, each recording that it stopped ([artifactr's serving guide](../../artifactr/guides/serving.md#adding-the-router)). Together, and with the rest of the shutdown, they must end within the app profile's `stop_grace_period`.

The **dev container** is built on `.devcontainer/compose.yaml`. When the stack is running, its `initialize.sh` adds the stack's networks and `stackr.env`'s addresses, so the application inside it reaches the stack by name; otherwise the dev container runs on its own.

## Keeping it up to date

### The template: `copier update`

```bash
uvx copier update
```

pulls in the template's improvements since the application was generated, keeping your own changes. An application generated before the portal existed is asked the `portal` question when it updates, and the default is yes: say no to keep the image as it is, since the portal adds a Bun stage to the build and a network fetch of lattice at the pinned commit. One generated before the forms is asked the `ui` question, also yes by default, which adds artifactr's `forms` extra, the types and checks, and four tools to the notes agent. It asks the questions again, with your previous answers (recorded in `.copier-answers.yml`) as the defaults; `--skip-answered` asks only the new ones. It needs a git repository with no uncommitted changes, and marks conflicts between the template's changes and yours inline, for you to resolve. Review the result like any other change, and run `make check`.

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

- **`make validate`** renders all sixteen variants (three choices of libraries, with and without evals, with grantr or without access control, both libraries without the bridge, both hosted on a single host, both with grantr and without the portal, and both without the forms) with `scripts/check-template`, under a name whose slug is the longest Copier accepts and whose package sorts before `conftest`, and checks that nothing is left unrendered, that the libraries come from lattice at the commit it was rendered from, that the Python passes the generated project's own ruff settings, and that the YAML, shell scripts and Compose file pass their linters.
- **CI's template job** generates each variant with grantr, the largest again on Python 3.14, again without access control, again without the portal, and again without the forms, and runs its own `make check`: lint, strict types, and the tests with 100% coverage. `scripts/check-app` sets `libraries_path`, so the application installs the libraries from the checkout, and the job runs when stackr or any library changes. A library's change and the template's then land in one pull request, checked together.
- **`stackr:access-matrix`** checks that the template's `access.md`, which it renders for each choice of libraries, matches the libraries' catalogs and grantr's roles; `scripts/access-matrix` rewrites it.
- **`make smoke-app`** generates an application with both libraries, evals and the bridge, which installs the libraries from GitHub at `HEAD`, as an application generated from lattice does (so `HEAD` must be pushed and the working tree clean; in CI, it is the pull request's merge commit). It runs it in its app profile beside the whole stack, with its portal (it serves both UIs, and asks grantr before a read), creates two tenants with its own command, signs a user in to the one they own and has them refused the other, traces its agents through the gateway into Tempo and Langfuse, and plays an incident through the bridge, from its alert to its proposed postmortem, and a rule from chat, from its draft to its notice ([The smoke tests](smoke-tests.md)).

To render and check one variant locally, from lattice's root, whose `copier.yml` points Copier at the template, with the libraries from the checkout:

```bash
uv run copier copy --defaults --vcs-ref HEAD --data libraries=both --data libraries_path="$PWD/packages" . /tmp/my-app
cd /tmp/my-app && git init && make install && make check
```
