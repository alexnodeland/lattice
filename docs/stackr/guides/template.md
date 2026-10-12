# The application template

stackr's [Copier](https://copier.readthedocs.io) template generates an application on artifactr, reflexr or both, wired to the stack's ports and nothing else: Supabase for sign-in and PostgreSQL, the gateway for models, the Collector for telemetry, and Langfuse for feedback and experiments ([ADR-0004](../adr/0004-the-application-template.md), [ADR-0011](../adr/0011-the-application-template-in-detail.md), [ADR-0015](../adr/0015-telemetry-mirrors-shutdown-and-namespaces-in-the-template.md)). Its questions are in stackr's `copier.yml`, which the `copier.yml` at lattice's root includes, since Copier reads a repository's root, and its files in `template/`.

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
| Identity | `auth.py` | Supabase's access tokens, verified against its published keys (`AUTH_JWKS_URL`), or with a legacy HS256 secret (`AUTH_JWT_SECRET`). The user is `sub` and the tenant `app_metadata.tenant_id`; anything else is 401, the MCP servers included |
| Database | `database.py` | The libraries' SQL storage on `DATABASE_URL`, migrated at startup, in a schema of the application's own (`DATABASE_SCHEMA`) |
| Telemetry | `telemetry.py` | `configure_telemetry` when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, once for both libraries (artifactr's, given reflexr's contribution): FastAPI, SQLAlchemy and httpx traced, the application and its engine included, and the libraries' polling untraced. Langfuse's client when `LANGFUSE_PUBLIC_KEY` is set too, for trace attributes and scores only (`langfuse="scores"`), since traces reach Langfuse through the Collector |
| Gateway | `gateway.py` | Agents on `litellm_model("default")`, each request with its tenant's key and the `pii-mask` and `prompt-injection` guardrails. A mocked reply, for smoke tests, is in the model's settings |
| Feedback | `scores.py` | Each workspace's feedback mirrored to Langfuse scores through evalr's `LangfuseScoreSink`, a score per field by evalr's score mapping, from the first request that uses it, over REST, the WebSocket or MCP. Each mirror saves its cursor, `langfuse`, in the workspace, and carries on after it when the application restarts. The feedback types' score configs are created at startup |
| Evals | `evals/` | The agents on a few examples, judged by evaluators whose verdicts are the application's own feedback types: offline with a scripted model (`make evals`), or in Langfuse with the gateway's model (`make evals-langfuse`) |
| Quality gates | `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml` | uv, ruff, pyright in strict mode, pytest with warnings as errors and 100% branch coverage, Conventional Commits. The tests need no network and no stack |
| The `app` profile | `compose.yaml`, `Dockerfile` | The application beside the stack, on its networks |
| Dev container | `.devcontainer/` | Joins the stack's networks when the stack is running |

Every surface is mounted under its library's name in every variant, so a variant, or a later `copier update`, never moves a URL, and both libraries mount side by side without clashing.

### Settings

The application reads the stack's ports from its environment ([`settings.py`](https://github.com/alexnodeland/lattice/blob/main/packages/stackr/template/src/%7B%7B%20package_name%20%7D%7D/settings.py.jinja)); `.env.example` has every setting, with the stack's addresses on this machine:

| Port | Settings |
|---|---|
| Telemetry | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_METRIC_EXPORT_INTERVAL` |
| Database | `DATABASE_URL`, `DATABASE_SCHEMA` |
| Identity | `AUTH_JWKS_URL`, `AUTH_ISSUER`, `AUTH_AUDIENCE`, `AUTH_JWT_SECRET`, `AUTH_TENANT_CLAIM` |
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

The **app profile** is the application's own `compose.yaml`, not a service in stackr's. Its service joins the `stackr` network and local Supabase's, and reads [`stackr.env`](https://github.com/alexnodeland/lattice/blob/main/packages/stackr/template/stackr.env) after `.env`, which replaces the stack's addresses in `.env` with their names on those networks. Its `DATABASE_URL` is local Supabase's PostgreSQL by name, unless `STACK_DATABASE_URL` in `.env` names another database.

So start the stack first, with local Supabase: stackr's default `make up`. The image is built in two stages, the first with git to fetch the libraries at their pinned commits, so building it needs the network.

**Stopping:** the server lets open requests finish for `DRAIN`. Then each library's MCP server stops, then its work, then its feedback mirrors, and the database closes last ([ADR-0015](../adr/0015-telemetry-mirrors-shutdown-and-namespaces-in-the-template.md)). reflexr's reactor gives running actions `STOP_GRACE` to end, and records those it then cancels as abandoned attempts, which the next start retries ([reflexr's graceful stop](../../reflexr/guides/reactor.md#running-the-reactor)). artifactr's runner stops the agent's turns still going, each recording that it stopped ([artifactr's serving guide](../../artifactr/guides/serving.md#adding-the-router)). Together, and with the rest of the shutdown, they must end within the app profile's `stop_grace_period`.

The **dev container** is built on `.devcontainer/compose.yaml`. When the stack is running, its `initialize.sh` adds the stack's networks and `stackr.env`'s addresses, so the application inside it reaches the stack by name; otherwise the dev container runs on its own.

## Keeping it up to date

### The template: `copier update`

```bash
uvx copier update
```

pulls in the template's improvements since the application was generated, keeping your own changes. It asks the questions again, with your previous answers (recorded in `.copier-answers.yml`) as the defaults; `--skip-answered` asks only the new ones. It needs a git repository with no uncommitted changes, and marks conflicts between the template's changes and yours inline, for you to resolve. Review the result like any other change, and run `make check`.

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

- **`make validate`** renders all six variants (three choices of libraries, with and without evals) with `scripts/check-template`, under a name whose slug is the longest Copier accepts and whose package sorts before `conftest`, and checks that nothing is left unrendered, that the libraries come from lattice at the commit it was rendered from, that the Python passes the generated project's own ruff settings, and that the YAML, shell scripts and Compose file pass their linters.
- **CI's template job** generates each variant, and the largest again on Python 3.14, and runs its own `make check`: lint, strict types, and the tests with 100% coverage. `scripts/check-app` sets `libraries_path`, so the application installs the libraries from the checkout, and the job runs when stackr or any library changes. A library's change and the template's then land in one pull request, checked together.
- **`make smoke-app`** generates an application with both libraries and evals, which installs them from GitHub at `HEAD`, as an application generated from lattice does (so `HEAD` must be pushed and the working tree clean; in CI, it is the pull request's merge commit). It runs it in its app profile beside the whole stack, and traces its agents through the gateway into Tempo and Langfuse ([The smoke tests](smoke-tests.md)).

To render and check one variant locally, from lattice's root, whose `copier.yml` points Copier at the template, with the libraries from the checkout:

```bash
uv run copier copy --defaults --vcs-ref HEAD --data libraries=both --data libraries_path="$PWD/packages" . /tmp/my-app
cd /tmp/my-app && git init && make install && make check
```
