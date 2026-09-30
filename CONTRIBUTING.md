# Contributing to lattice

Thanks for helping. lattice holds the family's packages, and this guide covers all of them: how to set up, the commands each package has, how work flows into `main`, and what "done" means here.

## Set up

You need [uv](https://docs.astral.sh/uv/), `make`, and [moon](https://moonrepo.dev/moon) at the version in `.prototools` ([proto](https://moonrepo.dev/proto) installs moon and uv from it: `proto use`). Everything else is installed from `uv.lock`. Docker runs the PostgreSQL tests and stackr's stack.

```bash
git clone git@github.com:alexnodeland/lattice.git
cd lattice
make install        # every package, example, dependency group and extra, in one environment
make check          # every project's checks, as CI runs them
```

## Commands

moon runs every task, from any directory: `moon run <project>:<task>`, or `moon run :<task>` for every project that has it. It runs only what a change affects, and caches the rest. `moon project <project>` lists a project's tasks. The projects are the packages (`artifactr`, `reflexr`, `evalr`, `relayr`, `stackr`), the reference implementations (`docplan`, `oncall`), and `lattice`, the root.

Every Python project has these:

| Task | What it does |
|---|---|
| `lint` | Check formatting and lint rules |
| `typecheck` | Type-check with pyright (strict for `src/` and `scripts/`) |
| `test` | Run the tests with the 100% branch-coverage gate |
| `format` | Format the code and apply safe lint fixes |
| `check` | Everything CI runs for the project |

Every package that ships a wheel also has `build`, which builds it as it is published; `standalone`, which installs the wheel with its extras, and its siblings' wheels, outside the workspace, then imports every module; and `deptry`, which fails on an import the package doesn't declare. `check` runs both.

The packages' own tasks:

| Task | What it does |
|---|---|
| `artifactr:schema`, `reflexr:schema` | Regenerate the protocol's JSON Schemas from the models (a test fails if they drift) |
| `artifactr:dashboards`, `reflexr:dashboards` | Regenerate the Grafana dashboards in `deploy/grafana/dashboards/` (a test fails if they drift) |
| `artifactr:pg-up`, `reflexr:pg-up` | Start PostgreSQL for the SQL tests, from the package's `compose.yaml` |
| `artifactr:test-pg`, `reflexr:test-pg` | Run the tests on PostgreSQL as well as SQLite |
| `artifactr:app-up`, `reflexr:app-up` | Build and start the reference implementation on PostgreSQL, at <http://localhost:8000> |
| `artifactr:pg-down`, `reflexr:pg-down` | Stop the package's contributor stack |
| `docplan:image`, `oncall:image` | Build the reference implementation's image from the root, start it on PostgreSQL and stop it, as CI's Images job does |
| `lattice:docs` | Build the documentation site in strict mode, and check that its lists rendered |
| `lattice:docs-serve` | Serve the documentation site with live reload at <http://localhost:8000> |

stackr keeps its Makefile for the stack: run `make` in `packages/stackr` to list its commands (`make env`, `make up`, `make validate`, `make smoke` and the rest). Its checks are moon tasks too: `stackr:validate`, and `stackr:reference`, which checks the documentation's reference pages against the files they describe.

### Testing SQL storage on PostgreSQL

artifactr's and reflexr's storage tests run against in-memory storage, SQLite and PostgreSQL. SQLite needs nothing extra, and it alone reaches the coverage gate. The PostgreSQL tests run only when `ARTIFACTR_TEST_POSTGRES_URL` or `REFLEXR_TEST_POSTGRES_URL` is set (otherwise pytest reports them as deselected), and CI always runs them.

```bash
moon run artifactr:pg-up        # postgres:17 on localhost:54329 (reflexr's is on 54330)
moon run artifactr:test-pg      # the whole suite, with the PostgreSQL tests included
moon run artifactr:pg-down
```

To use another database, set the variable yourself, for example `postgresql+asyncpg://user:password@host:5432/db`, and run `moon run artifactr:test`. Each test creates its own schema there and drops it afterwards. Give each library its own database.

### The contributor stack and the dev container

Each library's `compose.yaml` holds what developing it needs: PostgreSQL by default, and its reference implementation under the `app` profile. The observability and LLM infrastructure (the OpenTelemetry Collector, Grafana, Langfuse, LiteLLM) is stackr's. Its stack runs on a Docker network named `stackr`, and a library's `compose.stackr.yaml` puts its reference implementation on that network:

```bash
cd packages/artifactr
docker compose -f compose.yaml -f compose.stackr.yaml --profile app up -d --build
```

The dev container (`.devcontainer/`) has uv, moon and Docker, so everything above runs inside it too.

## How work flows: trunk-based development

`main` is the trunk and is always releasable ([artifactr ADR-0014][artifactr-adr-0014]).

1. Branch from the latest `main`. Keep branches short-lived: hours to a day or two, not weeks.
2. Keep pull requests small and focused on one change. Split large work into a sequence of PRs that each leave `main` green.
3. CI must pass before merging: its two required checks are `CI`, which passes only when every job does, and `Title`.
4. Pull requests are squash-merged, so the PR title becomes the commit on `main`. Write it as a [Conventional Commit](https://www.conventionalcommits.org/).
5. Delete the branch after merging. Don't stack branches on unmerged branches.

A change that spans packages lands in one pull request, so the packages never disagree on `main`. Unfinished features land behind unexported code paths or not at all; never on a long-lived branch.

### Commit messages

Commits and PR titles follow Conventional Commits, checked by a `commit-msg` hook and by the `Title` check:

```
feat(core): add anchored text edits for Markdown artifacts
fix(gateway): reach local model servers through host.docker.internal
docs(adr): record the documentation tooling decision
```

Types: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`. Scopes are a package's module or area names, as each package used them before (`core`, `workspace`, `mcp`, `scores`, `template`, ...); the paths a commit touches say which packages it belongs to. Mark breaking changes with `!` (`feat(core)!: ...`) and a `BREAKING CHANGE:` footer.

Each package's `CHANGELOG.md` is written from these messages by release-please, which keeps a release pull request open with what is pending. Don't edit a `CHANGELOG.md` by hand.

## Dependencies

Each package's `pyproject.toml` states the **oldest** versions it supports, as wide as correctness allows, so applications can resolve it alongside their own dependencies. A package names a sibling with a normal range in `[project]`, and `[tool.uv.sources]` takes the sibling from the workspace, which only development sees. `uv.lock` pins what CI and contributors run, one resolution for every package, and Renovate keeps the lockfile (not the ranges) current. Raise a lower bound only when the code needs a newer feature or fix, in the same pull request as that code.

## Design: RFCs, ADRs and evergreen docs

Each package's documentation is in `docs/<package>/`, with its RFCs in `rfcs/`, its ADRs in `adr/` and its architecture in `architecture.md`. An ADR or an RFC keeps its package's numbering, and outside its package it is named with the package, as in "reflexr ADR-0003".

| Document | When |
|---|---|
| **RFC** | Before a substantial change: new public API, protocol changes, a new package, cross-cutting behaviour |
| **ADR** | When a decision is made, including decisions made while implementing an RFC |
| **Architecture docs** | Updated in the same PR as the code they describe |

An RFC proposes; ADRs record what was decided; the architecture docs describe what exists now. Accepted ADRs are not edited; a changed decision gets a new ADR that supersedes or amends the old one.

Markdown is read on GitHub and on the documentation site, which renders it with Python-Markdown. Put a blank line before every list, including one that follows a paragraph, and indent a nested item by its parent's text: two spaces after `-`, three after `1.`. `moon run lattice:docs` fails on a list that rendered as text.

## Quality gates

These are enforced by CI, for every package, and described in each package's quality ADR ([artifactr ADR-0015][artifactr-adr-0015] and its siblings):

- **100% branch coverage** of each package's `src/`, and of each reference implementation's, each measured by its own tests. The only exclusions are configured in each `pyproject.toml` (type-checking blocks, protocol stubs, overloads, `assert_never`).
- **pyright strict** for `src/` and `scripts/`, standard for `tests/`.
- **ruff** for formatting and linting, with one configuration at the root, and Google-style docstrings on public API.
- **No inline suppressions** in any Python in the repository: no `# type: ignore`, `# pyright: ignore`, `# noqa` or `# pragma: no cover`. Restructure the code instead; the root's `tests/test_quality.py` fails on any. Per-file ignores in the root `pyproject.toml` are configuration, reviewed as such.
- **Warnings are errors** in the test suites.
- **The libraries stay independent.** Each library's layering test lists what each of its modules may import, deptry fails on an import a package doesn't declare, and each package's `standalone` task installs it outside the workspace.

## Definition of done

- [ ] Tests cover the change, and `make check` passes locally.
- [ ] Public API has docstrings and type annotations.
- [ ] The architecture docs of every package it touches reflect the change.
- [ ] New decisions have an ADR; substantial proposals had an RFC.
- [ ] The PR title is a Conventional Commit.

## Reporting bugs and proposing features

Use the issue forms, which ask which package. For security issues, follow [SECURITY.md][security] instead of opening a public issue.

## Code of conduct

This project follows the [Code of Conduct][code-of-conduct]. By participating, you agree to uphold it.

## License

By contributing, you agree that your contributions are licensed under the [MIT License][license].

<!-- Link targets live here so the documentation site can redefine them for its own layout. -->

[artifactr-adr-0014]: docs/artifactr/adr/0014-trunk-based-development-with-rfcs-and-adrs.md
[artifactr-adr-0015]: docs/artifactr/adr/0015-quality-gates.md
[code-of-conduct]: CODE_OF_CONDUCT.md
[license]: LICENSE
[security]: SECURITY.md
