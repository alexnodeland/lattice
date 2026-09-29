# The application template

stackr's [Copier](https://copier.readthedocs.io) template generates an application on artifactr, reflexr or both, wired to the stack's ports and nothing else: Supabase for sign-in and PostgreSQL, the gateway for models, the Collector for telemetry, and Langfuse for feedback and experiments ([ADR-0004](../adr/0004-the-application-template.md), [ADR-0011](../adr/0011-the-application-template-in-detail.md)). Its questions are in `copier.yml` at the repository's root, and its files in `template/`.

## Generate an application

```bash
uvx copier copy gh:alexnodeland/stackr my-app    # or a path to a clone of stackr
cd my-app
git init
make install        # uv sync, which writes uv.lock (commit it), and the git hooks
make env            # .env from .env.example
make check          # lint, types and tests, as its CI runs them
```

- **Which version.** Copier uses the template's latest release tag. stackr has none yet, so Copier warns that it found no tags and uses `main`. From a clone, `--vcs-ref HEAD` takes the checkout as it is, uncommitted changes included, which is how stackr's own checks render it.
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
| `artifactr_rev`, `reflexr_rev`, `evalr_rev` | Each library's `main` when the template was last updated | The git commit each library is pinned to, since none is on PyPI yet |

Answer non-interactively with `--defaults` and `--data`, as CI does:

```bash
uvx copier copy --defaults --data libraries=reflexr --data evals=false gh:alexnodeland/stackr my-app
```

[Template questions](../reference/template.md) lists every question with its choices, validation and the files each answer generates.

## What it generates

| Part | Where | What |
|---|---|---|
| Surfaces | `app.py`, `collaboration.py`, `automation.py` | FastAPI with each library's REST and WebSocket routes and MCP server, under its name: `/artifactr/v1`, `/artifactr/mcp/`, `/reflexr/v1`, `/reflexr/mcp/`. reflexr's reactor runs while the application is up |
| Examples | `notes.py`, `tickets.py` | A `note` artifact type, its agent and a `rating` of turns (artifactr); `ticket.opened` and `ticket.triaged` events, a `triage` rule, its agent, and a `triage-review` of runs (reflexr) |
| Identity | `auth.py` | Supabase's access tokens, verified against its published keys (`AUTH_JWKS_URL`), or with a legacy HS256 secret (`AUTH_JWT_SECRET`). The user is `sub` and the tenant `app_metadata.tenant_id`; anything else is 401, the MCP servers included |
| Database | `database.py` | The libraries' SQL storage on `DATABASE_URL`, migrated at startup, in a schema of the application's own (`DATABASE_SCHEMA`) |
| Telemetry | `telemetry.py` | `configure_telemetry` when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; Langfuse's client when `LANGFUSE_PUBLIC_KEY` is set too, for trace attributes and scores |
| Gateway | `gateway.py` | Agents on `litellm_model("default")`, each request with its tenant's key and the `pii-mask` and `prompt-injection` guardrails |
| Feedback | `scores.py` | Each workspace's feedback mirrored to Langfuse scores, from the first request that uses it, and the feedback types' score configs, created at startup |
| Evals | `evals/` | The agents on a few examples, judged by evaluators whose verdicts are the application's own feedback types: offline with a scripted model (`make evals`), or in Langfuse with the gateway's model (`make evals-langfuse`) |
| Quality gates | `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml` | uv, ruff, pyright in strict mode, pytest with warnings as errors and 100% branch coverage, Conventional Commits. The tests need no network and no stack |
| The `app` profile | `compose.yaml`, `Dockerfile` | The application beside the stack, on its networks |
| Dev container | `.devcontainer/` | Joins the stack's networks when the stack is running |

Every surface is mounted under its library's name in every variant, so a variant, or a later `copier update`, never moves a URL, and both libraries mount side by side without clashing.

### Settings

The application reads the stack's ports from its environment ([`settings.py`](https://github.com/alexnodeland/stackr/blob/main/template/src/%7B%7B%20package_name%20%7D%7D/settings.py.jinja)); `.env.example` has every setting, with the stack's addresses on this machine:

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

The **app profile** is the application's own `compose.yaml`, not a service in stackr's. Its service joins the `stackr` network and local Supabase's, and its compose file replaces the stack's addresses in `.env` with their names on those networks:

| Setting | In the app profile |
|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` |
| `LITELLM_BASE_URL` | `http://litellm:4000` |
| `LANGFUSE_BASE_URL` | `http://langfuse-web:3000` |
| `AUTH_JWKS_URL` | `http://supabase_kong_stackr-supabase:8000/auth/v1/.well-known/jwks.json` |
| `DATABASE_URL` | Local Supabase's PostgreSQL by name, or `STACK_DATABASE_URL` from `.env` for another database |

So start the stack first, with local Supabase: stackr's default `make up`. The image is built in two stages, the first with git to fetch the libraries at their pinned commits, so building it needs the network.

The **dev container** is built on `.devcontainer/compose.yaml`. When the stack is running, its `initialize.sh` adds the stack's networks and the same addresses, so the application inside it reaches the stack by name; otherwise the dev container runs on its own.

## Keeping it up to date

### The template: `copier update`

```bash
uvx copier update
```

pulls in the template's improvements since the application was generated, keeping your own changes. It asks the questions again, with your previous answers (recorded in `.copier-answers.yml`) as the defaults; `--skip-answered` asks only the new ones. It needs a git repository with no uncommitted changes, and marks conflicts between the template's changes and yours inline, for you to resolve. Review the result like any other change, and run `make check`.

### The libraries' revisions

Each library is pinned to a commit in `pyproject.toml`'s `[tool.uv.sources]`. `copier update` keeps the revisions you answered, even when the template's defaults move on, so to move a library forward, change its revision yourself:

```bash
uvx copier update --defaults --data artifactr_rev=<commit SHA>   # through Copier, recorded in the answers
# or edit the rev in pyproject.toml's [tool.uv.sources]
uv lock && make check
```

A revision is a full 40-character commit SHA. When an application uses reflexr's `[evals]` extra, it declares evalr's source itself, since reflexr's `[tool.uv.sources]` doesn't apply to the application's own requirements. It pins the commit reflexr's sources pin, since uv resolves reflexr's own requirement on evalr with them and refuses two URLs for one package, so move evalr with reflexr.

### In stackr: bumping the template's defaults

The libraries install from GitHub rather than PyPI for now ([artifactr#23](https://github.com/alexnodeland/artifactr/issues/23)), so the template's `*_rev` defaults in `copier.yml` follow each library's `main` by hand. `make bump-libraries` does it:

```bash
make bump-libraries                                  # every library, to the commit its main points to
make bump-libraries BUMP_FLAGS=--check               # change nothing; fail if a pin is behind main
make bump-libraries BUMP_FLAGS="artifactr=v0.1.0"    # artifactr only, to a tag, a branch or a commit SHA
```

It runs `scripts/bump-libraries`, which resolves each library's `main` with `git ls-remote`, rewrites the defaults in `copier.yml`, regenerates the reference pages that show them (`make docs-reference`), and prints each pin it moved, with a link to what changed:

```text
artifactr e890aca037c0 → 9c92a7f7685d  https://github.com/alexnodeland/artifactr/compare/e890aca037c0...9c92a7f7685d
```

Naming libraries moves only those; a commit SHA must be a full 40 characters, and is checked against the library's repository.

**evalr follows reflexr.** The template installs reflexr's `[evals]` extra, and uv resolves reflexr's requirement on evalr with reflexr's own `[tool.uv.sources]`, which pins evalr to a commit. An application whose own evalr pin names another commit has two URLs for one package, and uv refuses to lock it. So the script pins evalr to the commit the new reflexr pins, not to evalr's `main`, and says so when the two differ; evalr moves when reflexr moves its pin. Asking for another evalr commit is an error.

Then run `make validate`, and open a pull request with the output in its description: CI's template job generates every variant on the new revisions and runs its checks, and the smoke job runs an application on them beside the stack. When a library's `main` breaks the template, either fix the template in the same pull request, or pin that library to its last good commit.

Nothing runs this on a schedule, and CI doesn't run `--check`, which would fail every pull request as soon as a library merged something. Applications already generated keep their revisions until they move them, as above.

## How the template is checked

- **`make validate`** renders all six variants (three choices of libraries, with and without evals) with `scripts/check-template`, and checks that nothing is left unrendered, that the Python passes the generated project's own ruff settings, and that the YAML, shell scripts and Compose file pass their linters.
- **CI's template job** generates each variant, and the largest again on Python 3.14, and runs its own `make check`: lint, strict types, and the tests with 100% coverage.
- **`make smoke-app`** generates an application with both libraries and evals, runs it in its app profile beside the whole stack, and traces its agents through the gateway into Tempo and Langfuse ([The smoke tests](smoke-tests.md)).

To render and check one variant locally:

```bash
uv run copier copy --defaults --vcs-ref HEAD --data libraries=both . /tmp/my-app
cd /tmp/my-app && git init && make install && make check
```
