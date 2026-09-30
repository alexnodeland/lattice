# ADR-0011: The application template, in detail

**Status:** Accepted; partly superseded by [ADR-0013](0013-how-the-template-pins-the-libraries.md), [ADR-0015](0015-telemetry-mirrors-shutdown-and-namespaces-in-the-template.md) and [ADR-0016](0016-stackr-in-lattice.md)
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

## Context

[ADR-0004](0004-the-application-template.md) decided on a Copier template that generates applications on artifactr, reflexr or both, wired to the stack's ports ([ADR-0005](0005-ports-and-adapters-for-the-stack.md)), and RFC-0001 sketched what it generates. Building it settled what they left open, and found three things that differ from what was planned:

- **Copier takes a repository, not a directory in one.** RFC-0001's `copier copy gh:alexnodeland/stackr/template` becomes a clone of `https://github.com/alexnodeland/stackr/template.git`, which doesn't exist. A template in a subdirectory is declared by `_subdirectory` in a `copier.yml` at the repository's root.
- **Local Supabase signs access tokens with ES256.** The Supabase CLI pinned in `versions.env` (2.118.0) signs users' tokens with an asymmetric key and publishes it at `/auth/v1/.well-known/jwks.json`; its legacy JWT secret (HS256) signs only the API keys. Hosted projects that haven't moved to signing keys still sign with the secret.
- **Supabase's `public` schema is served to anyone with its public key.** Supabase's default privileges grant the `anon` and `authenticated` roles every privilege on tables the `postgres` role creates in `public`, and its Data API serves `public`. Local Supabase's ports listen on every interface ([ADR-0009](0009-local-supabase-as-the-database-adapter.md)), and its keys are well known.

Other questions were new: how the two libraries share one application, how feedback reaches Langfuse when each library mirrors one workspace at a time, how traces reach Langfuse when both the Collector and Langfuse's client can send them, and how a smoke test can run an agent through the gateway without a provider key.

## Decision

### The template

- **`copier.yml` at the repository's root, the files in `template/`.** Applications are generated with `uvx copier copy gh:alexnodeland/stackr my-app` (the latest release, once there are tags) or from a clone, and updated with `uvx copier update`. There are no Copier tasks, so no `--trust`.
- **Questions:** the name, slug and description; the libraries (`artifactr`, `reflexr` or `both`); whether to include evals; the Python version (3.12 to 3.14); the published port (8800 by default, since 8000 is commonly taken); and a revision for each library.
- **The libraries are pinned by git revision** in the application's `[tool.uv.sources]`, since none is on PyPI. The defaults are each repository's `main` when the template was last updated. The application declares evalr's source itself when it uses reflexr's `[evals]` extra: a dependency's own `[tool.uv.sources]` doesn't apply to its dependents.
- **One application, one database, one telemetry setup.** Each library's surfaces are mounted under its name in every variant: `/artifactr/v1` and `/artifactr/mcp/`, `/reflexr/v1` and `/reflexr/mcp/`. A variant, or a later `copier update`, never moves a URL, and both libraries mount side by side without clashing.
- **The examples are small and complete:** a `note` artifact type, its agent and a `rating` of turns (artifactr); `ticket.opened` and `ticket.triaged` events, a `triage` rule and its agent, and a `triage-review` of runs (reflexr). The triage agent answers in text, so a mocked model reply completes its run.

### The ports

- **Identity: Supabase's tokens, verified against its published keys, with a shared secret as well when one is set.** `AUTH_JWKS_URL` verifies asymmetric tokens (ES256, RS256, EdDSA and the rest) with the key their `kid` names; `AUTH_JWT_SECRET`, when set, verifies HS256 tokens. Each algorithm is verified only with its kind of key. Tokens must carry `exp`, `sub` and the `AUTH_AUDIENCE` (`authenticated`), and `AUTH_ISSUER` when it is set. The user is `sub`; the tenant is `app_metadata.tenant_id` (`AUTH_TENANT_CLAIM`), which only Supabase's service role can set. Anything else is 401: the libraries' routers answer 401 when `resolve_actor` refuses, and the MCP servers sit behind an ASGI guard that answers 401 before a request reaches them. A WebSocket, which browsers open without headers, may carry its token in the `access_token` query parameter. This amends ADR-0005's identity port, whose settings were `AUTH_ISSUER`, `AUTH_JWKS_URL` and `AUTH_AUDIENCE`, with `AUTH_JWT_SECRET` and `AUTH_TENANT_CLAIM`.
- **Database: `DATABASE_URL`, and the libraries' tables in a schema of the application's own.** `DATABASE_SCHEMA` (the package's name by default) is every connection's `search_path` and is created at startup, before the libraries' migrations run. Their tables and version tables are prefixed, so one schema holds both. Without a URL, workspaces live in memory; SQLite URLs use the libraries' SQLite engines.
- **Telemetry: `configure_telemetry`, when `OTEL_EXPORTER_OTLP_ENDPOINT` is set,** with Langfuse when `LANGFUSE_PUBLIC_KEY` is set too, so the application and its tests run without the stack. **Traces reach Langfuse only through the Collector**, as [ADR-0007](0007-how-telemetry-reaches-the-backends.md) routes every trace: the Langfuse client's span filter exports nothing, and the client still sets each turn's and run's session, user and tags on the spans and sends scores. (Turning its tracing off instead would stop its scores too.) FastAPI and HTTP clients are instrumented and the database driver is not, since the libraries poll their storage and each poll would be a trace of its own. With both libraries, artifactr's `configure_telemetry` sets up the one tracer and meter provider both use.
- **LLM gateway: `litellm_model("default")`, with the libraries' `LiteLLMGateway` capability.** Each request carries its tenant's key (`LITELLM_TENANT_KEYS`, a JSON object, or `LITELLM_API_KEY` for a tenant without one) and asks for the `pii-mask` and `prompt-injection` guardrails (`LITELLM_GUARDRAILS`). `LITELLM_MOCK_RESPONSE` adds LiteLLM's `mock_response` to every request, for smoke tests; the gateway honours it only for keys whose team allows mocked responses ([ADR-0010](0010-the-llm-gateway.md)).
- **Evaluation data: feedback mirrored to Langfuse scores, a mirror per workspace.** The libraries' `FeedbackMirror` follows one workspace; the application starts one for each workspace the first time a request uses it, through the routers' `authorize` hook, and creates the feedback types' score configs at startup. Neither stops the application when Langfuse is down.

### Around the application

- **Evals:** `evals/` holds starter experiments with evalr, whose evaluators' verdicts are the application's own feedback types: the notes agent's replies, and the triage rule replayed against the triage agent with reflexr's `replay_task`. They run offline with a scripted model and an in-memory tracker, or in Langfuse with the gateway's model.
- **Quality gates, as in the family:** uv, ruff, pyright in strict mode with no inline suppressions, pytest with warnings as errors and 100% branch coverage, pre-commit with Conventional Commits, and CI that runs them and builds the image. Tests need no network: tokens are signed in the test, and the model is scripted.
- **The `app` profile is the application's own Compose file.** Its service joins the `stackr` network and local Supabase's, where the stack's addresses are fixed; `.env` holds the addresses this machine uses, for `make serve`, and `STACK_DATABASE_URL` names another database for the profile. The image is built in two stages, the first with git for the libraries' sources.

### Validation

- **`make validate` renders every variant** (`scripts/check-template`) and checks that nothing is left unrendered, the Python passes the generated project's own ruff settings, the YAML passes yamllint, the shell scripts shellcheck, and the Compose file is valid.
- **CI's template job** generates each of the six variants and runs its `make check`, and the largest variant again on Python 3.14.
- **`make smoke-app`** generates an application with both libraries and evals, runs it in its app profile beside the whole stack, signs a user in with local Supabase Auth, and sends a message and a ticket. Each starts an agent whose model request goes through the gateway on a `stackr-smoke` key with a mocked reply. The smoke test checks that a request without a token is refused, that each agent's trace is in Tempo with the gateway's spans in it and in Langfuse, and that the application's turn and run counters are in Prometheus. It runs in CI with local Supabase only, the adapter whose Auth issues the tokens.

## Options considered

### Verifying access tokens

| Option | Local Supabase's tokens (ES256) | Hosted projects on the legacy secret (HS256) | Settings |
|---|---|---|---|
| **Published keys, and a shared secret when set (chosen)** | Yes | Yes | `AUTH_JWKS_URL`, `AUTH_JWT_SECRET` |
| A shared secret only (HS256) | No | Yes | `AUTH_JWT_SECRET` |
| Published keys only | Yes | No | `AUTH_JWKS_URL` |

### Where the libraries' tables live

| Option | Served by Supabase's Data API | Works on plain PostgreSQL and hosted Supabase | Settings |
|---|---|---|---|
| **A schema of the application's own (chosen)** | No | Yes | `DATABASE_URL`, `DATABASE_SCHEMA` |
| The `public` schema | Yes, to the anonymous role, unless row-level security is added to the libraries' tables | Yes | `DATABASE_URL` |
| A database of the application's own | No | Needs a role and database created by an administrator | `DATABASE_URL` |

### How traces reach Langfuse

| Option | Duplicates | Trace attributes and scores |
|---|---|---|
| **Through the Collector only; the client exports nothing (chosen)** | None | Kept |
| The client exports too | Every span twice | Kept |
| The client's tracing off | None | Scores stop too |

### Where the app profile lives

| Option | Generated applications | stackr |
|---|---|---|
| **The application's own Compose file, on the stack's networks (chosen)** | Run beside any stack that has the networks | Unchanged |
| A service in stackr's `compose.yaml`, built from a path | Depend on a checkout of stackr | Knows about one application |

## Consequences

- Easier: a new application starts signed in with Supabase, on its PostgreSQL out of the public schema's reach, traced end to end through the gateway, and scored in Langfuse, and passes its own CI.
- Easier: the smoke test proves the template, the libraries and the stack together, on every pull request.
- Harder: the template tracks the libraries' APIs and their `main` branches. When a library moves, bump its revision in `copier.yml`; the template job shows whether the generated applications still pass.
- Harder: the database driver isn't traced, so a turn's trace shows the libraries' commit spans but not their queries.
- Revisit: the libraries' storage polls, which keep the driver's instrumentation off; a mirror that follows every workspace, or keeps a cursor; published library releases, which would replace git revisions; and a smoke test on plain PostgreSQL, with tokens signed by the test.

## Action items

1. [x] The template, its checks in `make validate`, and CI's template job (RFC-0001 phase 5).
2. [x] `make smoke-app`, run by CI after the smoke test of everything on local Supabase.

## Amendment (2026-09-29): a script bumps the libraries' revisions

The maintainer decided to keep the libraries on GitHub rather than publish them to PyPI for now ([artifactr#23](https://github.com/alexnodeland/artifactr/issues/23)), so the template keeps pinning each by git revision, and published releases stay a reason to revisit. Bumping a pin by hand meant copying three commit SHAs into `copier.yml` and remembering `make docs-reference`, and the pins drifted: when the script below was added, all three were behind their libraries' `main`. So:

- **`scripts/bump-libraries` (`make bump-libraries`) moves the pins.** It resolves each library's `main` with `git ls-remote`, rewrites the `*_rev` defaults in `copier.yml`, and regenerates the reference pages that show them. `copier.yml` is the only place the pins are written: `template/pyproject.toml.jinja` reads them, and the pages are generated from them. It prints each change as old → new, with a URL comparing the two commits, for the pull request's description. `LIBRARY=REV` arguments move only the libraries they name, to a tag, a branch or a commit; a commit is checked by fetching it alone from the library's repository.
- **evalr follows reflexr.** Building the script found that the template's evalr pin can't follow evalr's `main`. The template installs reflexr's `[evals]` extra, and uv resolves reflexr's requirement on evalr with reflexr's own `[tool.uv.sources]`, which pins evalr to a commit; an application pinning evalr anywhere else has two URLs for one package, and uv refuses to lock it. The decision above, that an application declares evalr's source itself, stands, and the source must name the commit reflexr pins. So the script pins evalr to the commit the new reflexr's `pyproject.toml` pins, says so when evalr's `main` is elsewhere, and refuses an evalr revision that differs. evalr moves when reflexr moves its pin.
- **`--check` reports without writing,** and exits 1 when a pin is behind. Neither `make validate` nor CI runs it: every pull request would fail as soon as a library merged something, for a reason unrelated to the change.
- **A person runs it, and a pull request carries the bump.** No scheduled workflow opens bump pull requests: a workflow's token can open one only when the repository allows GitHub Actions to create pull requests, and that setting stays off. The pull request's Template and Smoke jobs, which generate applications on the new pins, are the test. When a library's `main` breaks the template, the same pull request fixes the template, or holds that library at its last good commit with `LIBRARY=REV`.

## Amendment (2026-09-29): the reactor stops gracefully

- **The reactor stops first, and never in the middle of a transaction.** `Automation.lifespan` runs reflexr's `reactor.serve(stop=, grace=)` ([reflexr#69](https://github.com/alexnodeland/reflexr/pull/69)) and, at shutdown, sets the event and awaits it before the feedback mirrors, the MCP server and the database close. Cancelling the reactor's task, as the template did, could land in a transaction and leave SQLite locked, which it caught and logged ([#17](https://github.com/alexnodeland/stackr/pull/17)).
- **The shutdown fits the stop period.** The server lets open requests finish for `DRAIN` (2 seconds, `app.py`), then the reactor gives running actions `STOP_GRACE` (5 seconds, `automation.py`); both, with the rest of the shutdown, end within the app profile's `stop_grace_period`, Docker's 10 seconds, which its compose file states.
