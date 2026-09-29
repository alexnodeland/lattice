# Contributing to artifactr

Thanks for helping. This guide covers how to set up, how work flows into `main`, and what "done" means here.

## Set up

You need [uv](https://docs.astral.sh/uv/) and `make`. Everything else is installed from `uv.lock`.

```bash
git clone git@github.com:alexnodeland/artifactr.git
cd artifactr
make install        # the library, the example app, every group and extra, and the git hooks
make check          # lint, types and tests: the same gates as CI
```

Run `make` on its own to list every command:

| Command | What it does |
|---|---|
| `make fmt` | Format the code and apply safe lint fixes |
| `make lint` | Check formatting and lint rules |
| `make typecheck` | Type-check with pyright (strict for `src/` and the example's code) |
| `make test` | Run the tests with the 100% branch-coverage gate |
| `make check` | Everything CI runs |
| `make docs` | Build the documentation site in strict mode and check that its lists rendered, as CI does |
| `make docs-serve` | Serve the documentation site with live reload at <http://localhost:8000> |
| `make schema` | Regenerate `schemas/artifactr.v1.json` from the protocol models (a test fails if it drifts) |
| `make dashboards` | Regenerate the Grafana dashboards in `deploy/grafana/dashboards/` from `scripts/grafana_dashboards.py` (a test fails if they drift). Each published release gets them as assets, and as `artifactr-dashboards-<version>.tar.gz` for stackr, from the `Release assets` workflow |
| `make pg-up` / `make pg-down` | Start or stop PostgreSQL for the SQL tests, from `compose.yaml` (needs Docker) |
| `make app-up` | Build and start docplan, the reference app, on PostgreSQL, at <http://localhost:8000> |
| `make test-pg` | Run the tests on PostgreSQL as well as SQLite |
| `make changelog` | Regenerate `CHANGELOG.md` from commit history |

### Testing SQL storage on PostgreSQL

The storage tests run against in-memory storage, SQLite and PostgreSQL. SQLite needs nothing extra, and it alone reaches the coverage gate. The PostgreSQL tests run only when `ARTIFACTR_TEST_POSTGRES_URL` is set (otherwise pytest reports them as deselected), and CI always runs them. Locally:

```bash
make pg-up          # compose.yaml's postgres:17, on localhost:54329 (PG_PORT=... to move it)
make test-pg        # the whole suite, with the PostgreSQL tests included
make pg-down
```

To use another database, set `ARTIFACTR_TEST_POSTGRES_URL` yourself, for example `postgresql+asyncpg://user:password@host:5432/db`. Each test creates its own schema there and drops it afterwards.

### The contributor stack and the dev container

`compose.yaml` holds what developing artifactr needs ([ADR-0030][adr-0030]): PostgreSQL by default, and docplan, the reference app, under the `app` profile.

```bash
docker compose up -d --wait                  # PostgreSQL, as make pg-up does
docker compose --profile app up -d --build   # and docplan on :8000 (make app-up)
```

docplan picks its model from `DOCPLAN_MODEL` and the provider's key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) in your environment.

The dev container (`.devcontainer/`) is built on the same file: PostgreSQL runs beside it, and `ARTIFACTR_TEST_POSTGRES_URL` points at it, so `make test` includes the PostgreSQL tests.

**With stackr.** The observability and LLM infrastructure (the OpenTelemetry Collector, Grafana, Langfuse, LiteLLM) lives in [stackr](https://github.com/alexnodeland/stackr), not here. Its stack runs on a Docker network named `stackr`:

- The dev container joins that network when it exists as the container is created, and sets `OTEL_EXPORTER_OTLP_ENDPOINT` to stackr's Collector and `LANGFUSE_BASE_URL` to its Langfuse. `.devcontainer/initialize.sh` checks on the host, so start stackr first, or rebuild the container after starting it.
- docplan joins it with the stackr overlay:

  ```bash
  docker compose -f compose.yaml -f compose.stackr.yaml --profile app up -d --build
  ```

CI validates every Compose file without starting containers.

## How work flows: trunk-based development

`main` is the trunk and is always releasable ([ADR-0014][adr-0014]).

1. Branch from the latest `main`. Keep branches short-lived: hours to a day or two, not weeks.
2. Keep pull requests small and focused on one change. Split large work into a sequence of PRs that each leave `main` green.
3. CI must pass before merging: lint, types, and tests at 100% coverage on every supported Python.
4. Pull requests are squash-merged, so the PR title becomes the commit on `main`. Write it as a [Conventional Commit](https://www.conventionalcommits.org/).
5. Delete the branch after merging. Don't stack branches on unmerged branches.

Unfinished features land behind unexported code paths or not at all; never on a long-lived branch.

### Commit messages

Commits and PR titles follow Conventional Commits, checked by a `commit-msg` hook:

```
feat(core): add anchored text edits for Markdown artifacts
fix(workspace): release the run lease when a run is cancelled
docs(adr): record the documentation tooling decision
```

Types: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`. Scopes are package or area names: `core`, `telemetry`, `workspace`, `agent`, `scores`, `sql`, `fastapi`, `mcp`, `otel`, `langfuse`, `litellm`, `examples`, `deploy`, `docs`, `adr`, `rfc`. Mark breaking changes with `!` (`feat(core)!: ...`) and a `BREAKING CHANGE:` footer. The changelog is generated from these messages.

## Dependencies

`pyproject.toml` states the **oldest** versions artifactr supports, as wide as correctness allows, so applications can resolve it alongside their own dependencies. `uv.lock` pins what CI and contributors run, and Dependabot keeps the lockfile (not the ranges) current. Raise a lower bound only when the code needs a newer feature or fix, in the same pull request as that code.

## Design: RFCs, ADRs and evergreen docs

| Document | When | Where |
|---|---|---|
| **RFC** | Before a substantial change: new public API, protocol changes, a new package, cross-cutting behaviour | [`docs/rfcs/`][rfcs] |
| **ADR** | When a decision is made, including decisions made while implementing an RFC | [`docs/adr/`][adrs] |
| **Architecture docs** | Updated in the same PR as the code they describe | [`docs/architecture.md`][architecture], [`docs/protocol.md`][protocol] |

An RFC proposes; ADRs record what was decided; the architecture docs describe what exists now. A PR that changes behaviour described in the architecture docs updates them in the same PR, never in a later cleanup. Accepted ADRs are not edited; a changed decision gets a new ADR that supersedes or amends the old one.

Markdown is read on GitHub and on the documentation site, which renders it with Python-Markdown. Put a blank line before every list, including one that follows a paragraph, and indent a nested item by its parent's text: two spaces after `-`, three after `1.`. `make docs` fails on a list that rendered as text.

## Quality gates

These are enforced by CI and described in [ADR-0015][adr-0015]:

- **100% branch coverage** of `src/artifactr`. Code that cannot be reached by a test is usually code that should not exist. The only exclusions are configured in `pyproject.toml` (type-checking blocks, protocol stubs, overloads, `assert_never`).
- **pyright strict** for `src/`, standard for `tests/`.
- **ruff** for formatting and linting, with Google-style docstrings on public API.
- **No inline suppressions** in `src/`, `tests/`, `examples/` or `scripts/`: no `# type: ignore`, `# pyright: ignore`, `# noqa` or `# pragma: no cover`. Restructure the code instead; `tests/test_quality.py` fails on any. Per-file ignores in `pyproject.toml` are configuration, reviewed as such.
- **Warnings are errors** in the test suite.
- Core behaviour is specified by **conformance fixtures**; a change to core behaviour changes a fixture.

## Definition of done

- [ ] Tests cover the change, and `make check` passes locally.
- [ ] Public API has docstrings and type annotations.
- [ ] Architecture docs and the protocol spec reflect the change.
- [ ] New decisions have an ADR; substantial proposals had an RFC.
- [ ] The PR title is a Conventional Commit.

## Reporting bugs and proposing features

Use the issue templates. For security issues, follow [SECURITY.md][security] instead of opening a public issue.

## Code of conduct

This project follows the [Code of Conduct][code-of-conduct]. By participating, you agree to uphold it.

## License

By contributing, you agree that your contributions are licensed under the [MIT License][license].

<!-- Link targets live here so the documentation site can redefine them for its own layout. -->

[adr-0014]: docs/adr/0014-trunk-based-development-with-rfcs-and-adrs.md
[adr-0015]: docs/adr/0015-quality-gates.md
[adr-0030]: docs/adr/0030-compose-and-dev-containers.md
[adrs]: docs/adr/README.md
[architecture]: docs/architecture.md
[code-of-conduct]: CODE_OF_CONDUCT.md
[license]: LICENSE
[protocol]: docs/protocol.md
[rfcs]: docs/rfcs/README.md
[security]: SECURITY.md
