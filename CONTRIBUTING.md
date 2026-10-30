# Contributing to lattice

Thanks for helping. lattice holds the packages, and this guide covers all of them: how to set up, the commands each package has, how work flows into `main`, and what "done" means here.

## Set up

You need [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh), `make`, and [moon](https://moonrepo.dev/moon), at the versions in `.prototools` ([proto](https://moonrepo.dev/proto) installs moon, uv and Bun from it: `proto use`). Everything else is installed from `uv.lock` and `bun.lock`; Bun also runs the web tools, so you don't need Node.js. Docker runs the PostgreSQL tests and stackr's stack.

```bash
git clone git@github.com:alexnodeland/lattice.git
cd lattice
make install        # every package, example, dependency group and extra, in one environment, and the web packages
make check          # every project's checks, as CI runs them
```

## Commands

moon runs every task, from any directory: `moon run <project>:<task>`, or `moon run :<task>` for every project that has it. It runs only what a change affects, and caches the rest. `moon project <project>` lists a project's tasks. The projects are the packages (`artifactr`, `reflexr`, `evalr`, `relayr`, `grantr`, `stackr`, `portalr`), portalr's web packages (`client`, `ui`, `app`, `admin`), the reference implementations (`docplan`, `oncall`), and `lattice`, the root.

Every Python project has these:

| Task | What it does |
|---|---|
| `lint` | Check formatting and lint rules |
| `typecheck` | Type-check with pyright (strict for `src/` and `scripts/`) |
| `test` | Run the tests with the 100% branch-coverage gate |
| `format` | Format the code and apply safe lint fixes |
| `check` | Everything CI runs for the project |

Every web package has these, each run by Bun from `bun.lock`:

| Task | What it does |
|---|---|
| `lint` | Check formatting and lint rules with Biome |
| `typecheck` | Type-check with TypeScript 7, strict |
| `test` | Run the tests with Vitest (`client`'s unit tests, and `ui`'s in Chromium, light and dark). `ui`'s screenshots run only where `CI` is set, against Linux baselines: to make or update one, take the `ui-screenshots` artifact from a failed Check (web) job, review it, and commit its `-reference` (a new one) or `-actual` (a changed one) files under `packages/portalr/web/ui/src/__screenshots__/`, without that suffix |
| `build` | Build the app with Vite (`app` and `admin`) |
| `format` | Format the code and apply safe lint fixes with Biome |
| `check` | Everything CI runs for the project |

Every package that ships a wheel also has `build`, which builds it as it is published; `standalone`, which installs the wheel with its extras, and its siblings' wheels, outside the workspace, then imports every module; and `deptry`, which fails on an import the package doesn't declare. `check` runs both.

The packages' own tasks:

| Task | What it does |
|---|---|
| `artifactr:schema`, `reflexr:schema` | Regenerate the protocol's JSON Schemas from the models, and the REST surface's OpenAPI document from the router (a test fails if they drift) |
| `grantr:schema` | Regenerate the admin API's OpenAPI document from the router (a test fails if it drifts) |
| `portalr:schema` | Regenerate portalr's router's OpenAPI document (a test fails if it drifts) |
| `artifactr:dashboards`, `reflexr:dashboards` | Regenerate the Grafana dashboards in `deploy/grafana/dashboards/` (a test fails if they drift) |
| `artifactr:pg-up`, `reflexr:pg-up`, `grantr:pg-up`, `relayr:pg-up` | Start PostgreSQL for the SQL tests, from the package's `compose.yaml` |
| `artifactr:test-pg`, `reflexr:test-pg`, `grantr:test-pg`, `relayr:test-pg` | Run the tests on PostgreSQL as well as SQLite |
| `relayr:vikunja-up`, `relayr:test-vikunja` | Start Vikunja on port 54333, from relayr's `compose.yaml`, and run the tracker contract test against it, live; with `RELAYR_RECORD=1`, its recorded exchanges are made again |
| `artifactr:app-up`, `reflexr:app-up` | Build and start the reference implementation on PostgreSQL, at <http://localhost:8000> |
| `artifactr:pg-down`, `reflexr:pg-down`, `grantr:pg-down`, `relayr:pg-down` | Stop the package's contributor stack |
| `artifactr:api`, `reflexr:api` | Start the reference implementation on PostgreSQL, run the package's Bruno collection and Schemathesis against it, and stop it, as CI's Acceptance job does. It needs Docker |
| `docplan:image`, `oncall:image` | Build the reference implementation's image from the root, start it on PostgreSQL, as a compose project of its own, and stop it, as CI's Images job does |
| `portalr:api` | Start portalr's test application beside Tempo, Loki, Prometheus and prom-label-proxy, seed two tenants, run its Bruno collection with the tools up and down and Schemathesis, and stop it, as CI's Acceptance job does. It needs Docker |
| `app:bdd` | Build the UIs, start portalr's test application with Supabase Auth, sign up the scenarios' people, run the app's features through playwright-bdd, and stop it, as CI's Acceptance job does. It needs Docker, and installs Chromium for Playwright |
| `client:api` | Start docplan and oncall, and run portalr's client against them, as CI's Acceptance job does. It needs Docker |
| `client:types` | Regenerate the client's types from the packages' committed documents (a test fails if they drift) |
| `lattice:knip` | Find unused files, exports and dependencies in the web packages |
| `lattice:breaks` | Find the breaks the branch adds to the packages' public APIs, against their last releases |
| `lattice:docs` | Build the documentation site in strict mode, and check that its lists rendered |
| `lattice:docs-serve` | Serve the documentation site with live reload at <http://localhost:8000> |

The tasks that start a compose project, `app:bdd`, `admin:bdd`, `portalr:api`, `client:api`, each package's `api` and each reference implementation's `image`, give it a name with a random token of its own (`portalr-bdd-<token>`, `portalr-admin-bdd-<token>`, `<package>-api-<token>`, `portalr-api-<token>`, `portalr-docplan-<token>`, `portalr-oncall-<token>`, `docplan-image-<token>`, `oncall-image-<token>`; `scripts/compose-project.sh` derives it), so runs at once, such as ones in other worktrees, don't share a stack, and each removes what it started when it ends, on a signal too. A run killed outright (`SIGKILL`, a lost terminal) leaves its project behind. List the projects with `docker compose ls -a`, which only lists, and remove one by its exact name, from `packages/portalr/web/app` or `packages/portalr/web/admin`: `COMPOSE_FILE=../../compose.yaml COMPOSE_PROFILES=app,bdd,editor COMPOSE_PROJECT_NAME=<exact name> docker compose down --volumes --rmi local`. Any project, whichever task started it, can instead be removed by its exact name from anywhere with `docker compose -p <exact name> down --volumes`, which needs no compose file and leaves the image the run built.

stackr keeps its Makefile for the stack: run `make` in `packages/stackr` to list its commands (`make env`, `make up`, `make validate`, `make smoke` and the rest). Its checks are moon tasks too: `stackr:validate`, and `stackr:reference`, which checks the documentation's reference pages against the files they describe.

### Testing SQL storage on PostgreSQL

artifactr's, reflexr's and grantr's storage tests, and relayr's ledger tests, run against in-memory storage, SQLite and PostgreSQL. SQLite needs nothing extra, and it alone reaches the coverage gate. The PostgreSQL tests run only when `ARTIFACTR_TEST_POSTGRES_URL`, `REFLEXR_TEST_POSTGRES_URL`, `GRANTR_TEST_POSTGRES_URL` or `RELAYR_TEST_POSTGRES_URL` is set (otherwise pytest reports them as deselected), and CI always runs them.

```bash
moon run artifactr:pg-up        # postgres:17, as a compose project of its own on a port the system picks
moon run artifactr:test-pg      # the whole suite, with the PostgreSQL tests included
moon run artifactr:pg-down
```

`pg-up` names the compose project with a random token (`artifactr-pg-3f9a1c0e`) and records it in the package's `.pg-project`, so each worktree has a stack of its own; `test-pg` reads the URL from it (`scripts/pg url`), and `pg-down` removes only that project, with its volumes. `app-up` and relayr's `vikunja-up` join the same project.

To use another database, set the variable yourself, for example `postgresql+asyncpg://user:password@host:5432/db`, and run `moon run artifactr:test`. Each test creates its own schema there and drops it afterwards. Give each library its own database.

### The contributor stack and the dev container

Each library's `compose.yaml` holds what developing it needs: PostgreSQL by default, and its reference implementation under the `app` profile. The observability and LLM infrastructure (the OpenTelemetry Collector, Grafana, Langfuse, LiteLLM) is stackr's. Its stack runs on a Docker network named `stackr`, and a library's `compose.stackr.yaml` puts its reference implementation on that network:

```bash
cd packages/artifactr
docker compose -f compose.yaml -f compose.stackr.yaml --profile app up -d --build
```

The dev container (`.devcontainer/`) has uv, Bun, moon and Docker, so everything above runs inside it too.

## How work flows: trunk-based development

`main` is the trunk and is always releasable ([artifactr ADR-0014][artifactr-adr-0014]).

1. Branch from the latest `main`. Keep branches short-lived: hours to a day or two, not weeks.
2. Keep pull requests small and focused on one change. Split large work into a sequence of PRs that each leave `main` green.
3. CI must pass before merging: its two required checks are `CI`, which passes only when every job does, and `Title`.
4. Pull requests are squash-merged through the merge queue: once a pull request is reviewed and green, label it `queue` (or comment `@mergifyio queue`), and Mergify tests it with the others waiting and merges it ([lattice ADR-0016][lattice-adr-0016], [ADR-0024][lattice-adr-0024]; see [Merging](#merging)). The PR title becomes the commit on `main`. Write it as a [Conventional Commit](https://www.conventionalcommits.org/).
5. Delete the branch after merging. Don't stack branches on unmerged branches.

A change that spans packages lands in one pull request, so the packages never disagree on `main`. Unfinished features land behind unexported code paths or not at all; never on a long-lived branch.

### Merging

The queue is Mergify's, configured in `.mergify.yml` ([ADR-0024][lattice-adr-0024]). It tests the pull requests waiting together, in temporary draft pull requests (`mergify/merge-queue/...`) that hold a batch of one or two on top of `main`, two batches at a time, and squash-merges each pull request when its batch passes `CI`.

- **Queue a pull request** when it is reviewed, green and ready: add the `queue` label, or comment `@mergifyio queue`. Take it out with `@mergifyio dequeue`, or by removing the `queue` label, which dequeues it too. The median from the label to the merge was about eleven minutes in the last 40 merges (one `CI` run), and longer behind others.
- **Behind** (GitHub's "BEHIND") means the branch lacks the latest `main`. GitHub shows it only where the ruleset requires up-to-date branches, which it no longer does; the batch is tested on top of `main`, so you don't need to update the branch. If a pull request shows BEHIND and the queue refuses it, say so: the ruleset's requirement may have been turned back on.
- **A failed batch is bisected:** split in two and tested again until the pull request that broke it is found. That one is taken out of the queue with a comment from Mergify; fix it, push, and queue it again. The others merge. If yours is removed and its own `CI` was green, the failure was in how it combines with what was ahead of it: read the draft pull request's `CI` run, linked from Mergify's comment. Two pull requests that conflict in one batch are both taken out with a comment, not bisected.
- **Requeue after a flake with `@mergifyio requeue`, not the label.** A pull request taken out for a failed check keeps that failure in Mergify's memory: removing and re-adding `queue` takes it straight back out. Comment `@mergifyio requeue` (as on #1180; or tick "Requeue this pull request" in Mergify's comment), which resets its state and tests it again. `.mergify.yml` can't do this when the label is re-added: a rule could only post the same command as Mergify's own comment, and the docs don't say that Mergify acts on its own comments. The queue already retries a failed check once (`max_checks_retries: 1` in `.mergify.yml`): Mergify recreates the draft and runs `CI` again before it dequeues anything, so a single flake no longer needs a requeue; a pull request that fails twice is dequeued, and this note applies to it. A real failure costs one extra run, the price the owner chose.
- **Group related work into one pull request,** with a commit for each step. The queue's cost is per pull request, not per line, and a follow-up that touches the same files as an open pull request belongs in it (a docs cleanup, a rename's fallout, a config change and the docs that describe it). Keep the number of open pull requests low; split only what could be reverted or reviewed on its own.

### Commit messages

Commits and PR titles follow Conventional Commits, checked by a `commit-msg` hook and by the `Title` check:

```
feat(core): add anchored text edits for Markdown artifacts
fix(gateway): reach local model servers through host.docker.internal
docs(adr): record the documentation tooling decision
```

Types: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`. Scopes are a package's module or area names, as each package used them before (`core`, `workspace`, `mcp`, `scores`, `template`, ...); the paths a commit touches say which packages it belongs to. Mark breaking changes with `!` (`feat(core)!: ...`) and a `BREAKING CHANGE:` footer. The `Title` check compares each package's public API with its last release, through griffe, and fails on a break the pull request adds that neither the title nor the description marks; `moon run lattice:breaks` shows the same breaks locally ([lattice ADR-0012][lattice-adr-0012]).

Each package's `CHANGELOG.md` is written from these messages by release-please, which keeps one release pull request open with what is pending for every package; each package keeps its own version and changelog. Don't edit a `CHANGELOG.md` by hand.

## Dependencies

Each Python package's `pyproject.toml` states the **oldest** versions it supports, as wide as correctness allows, so applications can resolve it alongside their own dependencies. A package names a sibling with a normal range in `[project]`, and `[tool.uv.sources]` takes the sibling from the workspace, which only development sees. `uv.lock` pins what CI and contributors run, one resolution for every package, and Renovate keeps the lockfile (not the ranges) current. Raise a lower bound only when the code needs a newer feature or fix, in the same pull request as that code.

The web packages are private and pin exact versions, which `bun.lock` records and Renovate moves. A web package names a sibling as `"@portalr/ui": "workspace:*"`, and its `moon.yml` names it in `dependsOn`, which the root's tests check.

`make install` installs the web packages with `scripts/bun-install`: `bun install --frozen-lockfile`, as CI runs it, with the Bun `.prototools` pins. It fails, and says why, when the Bun on `PATH` is another version or when the install would change `bun.lock`, which it never changes itself. The one way to add, remove or move a JS dependency, and so change `bun.lock`, is Bun's own command run in the web package, with the pinned Bun on `PATH` (`proto use`):

```bash
cd packages/portalr/web/<package>   # or the root, for the shared tools (Biome, knip, TypeScript)
bun add --exact <name>@<version>    # or `bun add --exact --dev`, or `bun remove <name>`
```

Commit `bun.lock` with the `package.json` it belongs to, and nothing else in it.

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
- **TypeScript strict,** from `tsconfig.base.json`, and **Biome** for formatting and linting, in the web packages; **knip** fails on an unused file, export or dependency.
- **No inline suppressions** in any Python in the repository: no `# type: ignore`, `# pyright: ignore`, `# noqa` or `# pragma: no cover`; nor in the TypeScript: no `@ts-expect-error`, `@ts-ignore`, `@ts-nocheck` or `biome-ignore`. Restructure the code instead; the root's `tests/test_quality.py` fails on any. Per-file ignores in the root `pyproject.toml` are configuration, reviewed as such.
- **Warnings are errors** in the test suites.
- **Tests run in a random order,** through pytest-randomly, and each run prints its seed. A test that fails in only some orders is reproduced with `uv run pytest --randomly-seed=N` and fixed; `-p no:randomly` runs the tests in file order ([lattice ADR-0010][lattice-adr-0010]). artifactr's, relayr's and grantr's moon `test` tasks run them on every core, through pytest-xdist (`--numprocesses auto`), while a plain `uv run pytest` runs them in one process, as `-n0` does. pytest-xdist is in the root's `dev` group, so sync with `--all-groups`, as CI does. Every worker collects the tests itself, so a test's id must be the same in every process: no time, address or unordered set in a parametrized case's bytes. Each worker shuffles its own share, so `--randomly-seed=N` reproduces an order only with the same number of workers. A test that runs for a minute fails by `SIGALRM`, with its traceback, and its worker carries on; the other threads' stacks go to the worker's own terminal, which xdist doesn't show, so a hang in another thread is found by running the test alone with `-o timeout_method=thread` ([lattice ADR-0028][lattice-adr-0028]). Each run lists its ten slowest tests, and one that needs longer says so with its own `pytest.mark.timeout` and why: a Hypothesis test with `method="thread"`, since Hypothesis replays a failure once the signal's timer is spent. `SIGALRM` is macOS's and Linux's: run the tests there, in the dev container, or through uv and moon, not on Windows.
- **Code scanning.** CodeQL analyses the Python and the TypeScript on every pull request, and its alerts show there. Fix each one, or dismiss it with its reason ([lattice ADR-0011][lattice-adr-0011]).
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
[lattice-adr-0010]: docs/adr/0010-every-projects-tests-run-in-a-random-order.md
[lattice-adr-0011]: docs/adr/0011-codeql-and-scorecard.md
[lattice-adr-0012]: docs/adr/0012-title-checks-the-breaks-in-the-public-apis.md
[lattice-adr-0016]: docs/adr/0016-a-merge-queue-on-mergify.md
[lattice-adr-0024]: docs/adr/0024-a-parallel-batched-merge-queue.md
[lattice-adr-0028]: docs/adr/0028-a-stuck-test-fails-by-a-signal-and-its-worker-carries-on.md
[license]: LICENSE
[security]: SECURITY.md
