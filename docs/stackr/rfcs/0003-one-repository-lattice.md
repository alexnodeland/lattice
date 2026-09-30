# RFC-0003: One repository: lattice

**Status:** Accepted
**Author:** Alex Nodeland
**Created:** 2026-09-30
**Discussion:** [#43](https://github.com/alexnodeland/stackr/pull/43); accepted on 2026-09-30, with the decisions in [Decisions](#decisions)
**Siblings:**

- [reflexr ADR-0003][r-adr-0003] keeps the libraries independent, with no shared kernel. lattice keeps that rule and enforces it with checks instead of repository walls.
- [ADR-0013](../adr/0013-how-the-template-pins-the-libraries.md) pins the template's libraries by git revision, with evalr as a special case. In lattice, one revision pins them all.
- [ADR-0014](../adr/0014-one-docs-build.md), with [evalr ADR-0013][e-adr-0013], [artifactr ADR-0050][a-adr-0050] and [reflexr ADR-0046][r-adr-0046], is the "one docs build" arrangement that the family site keeps.

## Summary

The family is seven repositories. Four are established: artifactr, reflexr, evalr and stackr. Three are new and nearly empty: relayr, grantr and portalr. This RFC moves them into one new public repository, **`alexnodeland/lattice`**, with the established packages' history and relayr's.

Every package stays what it is today: its own name, `pyproject.toml`, version, dependencies, extras, tests, 100% coverage gate, ADRs, RFCs, changelog and releases. **lattice only holds the packages. Every package stays installable on its own downstream:** from a subdirectory of lattice at a package tag now, and from PyPI later. CI proves this on every change.

moon runs the tasks. uv manages the Python packages as one workspace, and Bun manages portalr's TypeScript as another. One documentation site at `lattice.alexnodeland.com` has a section per package. The four old sites keep serving until they are retired separately.

The maintainer accepted the RFC on 2026-09-30 and settled every open question; [Decisions](#decisions) records them.

## Motivation

The libraries were kept apart on purpose ([reflexr ADR-0003][r-adr-0003]), and that rule is sound. Separate repositories were only one way to enforce it, and this week showed what that costs:

- **evalr's pin had to match across libraries.** artifactr and reflexr each pin evalr by commit, and when the pins differ, `uv lock` fails in any application that installs both ([ADR-0013](../adr/0013-how-the-template-pins-the-libraries.md)). So the pins moved in lockstep: to `c6866c4` in artifactr [#59][a-59] and reflexr [#70][r-70], three minutes apart, then to `7a29012` in artifactr [#70][a-70] and reflexr [#81][r-81], thirty seconds apart. Only then could stackr [#40][s-40] move the template onto both.
- **Pairs of pull requests merged in lockstep, with byte-identical code.** Six blocks in five files carry a "Shared verbatim with …; change both" note. Five pairs landed this week: artifactr [#64][a-64], [#67][a-67], [#69][a-69], [#70][a-70] and [#56][a-56], with reflexr [#73][r-73], [#76][r-76], [#79][r-79], [#80][r-80] and [#90][r-90].
- **Every library wave forced a stackr template bump.** [#36][s-36] and [#40][s-40] each moved the template onto the libraries' `main`, a day apart, and #40 adopted changes from eight pull requests in three repositories. Meanwhile, the template's code was only ever tested against the pins it already had.
- **Cross-repository RFCs live in stackr because they have no other home.** [RFC-0002](0002-the-combined-system.md) and this RFC belong to the family, not to the infrastructure template.
- **Seven CIs, docs sites and rulesets, and counting.** "One docs build" landed four times (evalr [#34][e-34], stackr [#38][s-38], artifactr [#71][a-71], reflexr [#85][r-85]), and the list rendering fix three times (artifactr [#43][a-43], reflexr [#55][r-55], evalr [#27][e-27]). relayr's unmerged foundation is 46 files, and its workflows, hooks, Makefile and changelog configuration are copies.

Now is the cheapest time to move. Three of the seven repositories hold almost nothing, and the four established ones have no open pull requests.

## Design

### Requirements

| Requirement | How it holds |
|---|---|
| Every package stays installable on its own | Its own metadata, version ranges between packages, and a standalone check in CI ([Standalone packages](#standalone-packages)) |
| The libraries stay independent (reflexr ADR-0003) | The existing layering tests, plus deptry over each package's shipped code ([The uv workspace](#the-uv-workspace)) |
| Each package keeps its gates | Its own tests and 100% coverage gate, under one shared lint, type and quality configuration |
| History is kept | Each established repository, and relayr's branch, is imported with its history, rewritten into its subdirectory ([Migration](#migration)) |
| ADRs and RFCs keep their numbers | Each package's ADRs and RFCs move with its docs. Family-level RFCs start a new series |

### Layout

```text
lattice/
├── packages/
│   ├── artifactr/          artifactr-ai: pyproject.toml, src/, tests/, bruno/, moon.yml, README.md, CHANGELOG.md, LICENSE
│   ├── reflexr/
│   ├── evalr/
│   ├── relayr/             relayr-ai
│   ├── grantr/
│   ├── stackr/             the stack and the Copier template: compose.yaml, supabase/, deploy/, scripts/, template/, copier.yml, Makefile
│   └── portalr/            pyproject.toml (the console service), src/portalr/, bruno/, web/ (app, admin, client, ui)
├── examples/
│   ├── docplan/            artifactr's reference implementation
│   └── oncall/             reflexr's reference implementation
├── docs/                   the site: the family's pages, and docs/<package>/ for each package, each with its own .nav.yml
├── tests/                  the family's checks: one quality test over all Python, and moon's edges against pyproject.toml
├── .devcontainer/          one dev container
├── .moon/                  workspace.yml, toolchains.yml, tasks/
├── .github/                workflows, issue and pull request templates
├── pyproject.toml          the uv workspace root (virtual): members, the shared ruff configuration, the family's tools
├── uv.lock, package.json, bun.lock, biome.json, tsconfig.base.json
├── mkdocs.yml, copier.yml, moon.yml, Makefile, .prototools, .pre-commit-config.yaml, .dockerignore
├── renovate.json, release-please-config.json, .release-please-manifest.json
└── README.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, LICENSE
```

- **`packages/<name>/` for every package,** stackr and portalr included. One rule is easy to glob, and a package's directory holds its code, tests, collection, changelog and license. The license stays in each package because its wheel and sdist ship it (`license-files`).
- **portalr is one directory.** The console service and the web tiers share a version, a tag and a changelog. The service is the `pyproject.toml` at portalr's root, and the Bun packages sit under `web/`, so no Python project is nested in another. The rest of portalr's design is for the portal RFC.
- **The reference implementations move to `examples/`.** In lattice, docplan and oncall would be uv workspace members inside another member, and uv 0.12.12 refuses that ("Project is contained in non-workspace project"; [uv #13298][uv-13298] and [uv #16640][uv-16640], both open). Each becomes its own moon project with its own 100% gate.
- **The docs live at the root** (see [Docs](#docs)), so a package's pages, ADRs included, leave its directory.
- **Family documents** go in `docs/`: `architecture.md` says how the packages relate and which imports are allowed, `rfcs/` starts the family's RFC series, and `adr/` holds family decisions. stackr's RFC-0001 to RFC-0003 keep their numbers in stackr's section. In family documents, an ADR or RFC is always named with its package, as in "reflexr ADR-0003".

### Standalone packages

lattice changes where the packages are developed, not what they are downstream.

| Property | How it holds |
|---|---|
| Package metadata | Each `pyproject.toml` keeps its name, version, dependencies and extras. relayr's distribution becomes `relayr-ai`, since `relayr` is taken on PyPI; it is still imported as `relayr` |
| Dependencies between packages | Normal ranges in `[project]`, such as `evalr>=0.2,<0.3`. `{ workspace = true }` appears only in `[tool.uv.sources]`, which is development-only. Verified with uv 0.12.12: a built wheel carries `Requires-Dist: evalr>=0.2,<0.3; extra == "evals"` and no path, and the sdist installs outside the workspace |
| Honest ranges | uv doesn't check a member's version against its dependents' ranges (a member at 0.3.0 satisfied `<0.3` without a word). The standalone check installs sibling wheels by path, so a dishonest range fails to resolve (verified) |
| Installable before PyPI | `git+https://github.com/alexnodeland/lattice@artifactr-v0.2.0#subdirectory=packages/artifactr`, or a uv git source with `subdirectory` and a tag. uv lowers the package's own `workspace = true` sources to the same repository and commit (verified), so `artifactr-ai[evals]` at a tag brings evalr from that commit. pip reads only the wheel's ranges, so pip users install evalr from git too, until it is on PyPI |
| Publishable later | A PyPI job in the release workflow, per package, with no change to the layout |

**The standalone check** is two moon tasks for every project tagged `distribution`:

- `build` runs `uv build --package <name> --no-sources`, with `dist/**` as its outputs, so each wheel is built once.
- `standalone` depends on `build` and `^:build`. It installs the wheel with its extras, and its siblings' wheels by path, into a fresh environment outside the workspace, then imports every module its extras enable and checks the version.

### The uv workspace

The root `pyproject.toml` is a virtual project (`package = false`) that lists the members (`packages/*` and `examples/*`) and holds the family's tools. stackr joins as a virtual member too (verified).

| | Seven repositories | lattice |
|---|---|---|
| A sibling dependency | A git URL and commit in `[tool.uv.sources]` | `{ workspace = true }`, installed editable, with the range kept in `[project]` |
| Lockfiles and evalr | One lock per repository, and evalr pinned twice | One `uv.lock`, and one evalr: the checkout's |
| Third-party versions | Resolved per repository | One resolution, so the packages must agree on every range. They agree today |
| Tool configuration | About 75 near-identical lines per library | One root `[tool.ruff]` (a package that needs its own ignores uses `extend`). Per package, only pytest's `testpaths` and coverage's `source`. pyright stays per package until ty replaces it with one root configuration |
| The quality test | A copy per repository, which stops seeing `examples/` once they move | One root test over every package, `examples/` and the root's own Python |

**Independence is enforced, not assumed.** In one environment every member is importable, so an undeclared import that used to fail with `ImportError` would now pass silently, and uv's documentation says it can't prevent this.

- **The existing layering tests** stay. artifactr's and reflexr's list the modules each layer may import, and evalr's forbid `artifactr` and `reflexr` by name.
- **deptry** checks each package's shipped code, run from the package's directory so its default exclusion of `tests/` applies. An undeclared import (DEP001, DEP003) or a development dependency used there (DEP004) fails. It catches undeclared third-party imports too, and the standalone check backs it up. DEP002 (unused) stays off, since extras such as `[postgres]` name drivers that the library never imports. Tests and scripts are left to the layering tests, since an undeclared sibling there doesn't affect installability.

**Out of scope: a shared package for the "shared verbatim" helpers.** It would be the shared kernel that reflexr ADR-0003 deferred, and it is a separate, later ADR. In lattice, one pull request changes both copies.

### The Bun workspace

portalr's TypeScript is a Bun workspace rooted at lattice's root, so TypeScript has one lockfile, as Python has one `uv.lock`.

| File | Holds |
|---|---|
| `package.json` | `"private": true`, `"workspaces": ["packages/portalr/web/*"]`, the `packageManager` field, and the shared dev tools: TypeScript 7.0 (the native compiler, which has no programmatic API yet; Biome lints, so nothing needs one), Biome, Vitest, fast-check, knip, size-limit and the Bruno CLI |
| `bun.lock` | The text lockfile, which moon's Bun toolchain reads, and which CI installs with `bun install --frozen-lockfile` |
| `biome.json`, `tsconfig.base.json` | Formatting and lint rules, and strict compiler options that each package extends |

### moon

moon runs every task, and only the ones a change affects. uv and Bun manage dependencies, and moon never edits a manifest or a lockfile.

| File | Holds |
|---|---|
| `.moon/workspace.yml` | The projects as an explicit map, including a root-level project, `lattice`. Also `vcs.defaultBranch: main` and a `versionConstraint` |
| `.moon/toolchains.yml` | `javascript` (`packageManager: bun`), `bun` and `typescript`, with `installDependencies: false` and the settings that rewrite files turned off. No Python toolchain (D3) |
| `.moon/tasks/python.yml` | For every project with `language: python` (which needs no toolchain): `lint`, `typecheck`, `test` and `check` |
| `.moon/tasks/typescript.yml` | For every web package: `lint`, `typecheck`, `test`, `build` and `check` |
| `.moon/tasks/<tag>.yml` | By tag: `build`, `standalone` and `deptry` for projects tagged `distribution`, and `api` for projects tagged `api` |
| `packages/<name>/moon.yml` | `language`, `layer`, `dependsOn` and tags. Its own tasks, such as stackr's `template` and `smoke`. The libraries' other Makefile targets (`schema`, `dashboards`, `pg-up`, `app-up`, `test-pg`) become tasks with `runInCI: false` and `cache: false` |
| `moon.yml` (root) | The `lattice` project: `docs`, one `knip` run over the Bun workspace, and the family's tests |
| `.prototools` | The versions of moon, uv and Bun, which CI installs through `moonrepo/setup-toolchain` and Renovate's `proto` manager updates |

`check` is one task per project that runs nothing itself (`command: 'noop'`) and depends on the project's other checks. CI runs `:check`, and the root Makefile's `check` runs `moon run :check`, so the list lives in one place.

**Edges are explicit.** moon's Python toolchain would infer an edge only from a requirement with neither a version nor a URL, and lattice's requirements carry ranges. So every `moon.yml` states `dependsOn`, and a root test fails when it disagrees with the workspace dependencies in the project's `pyproject.toml`.

| Project | `dependsOn` |
|---|---|
| evalr, grantr | none |
| artifactr, reflexr | evalr |
| relayr | artifactr, reflexr |
| docplan, oncall | artifactr, reflexr respectively |
| stackr | artifactr, reflexr and evalr (its template generates applications on them), and relayr once the template wires it in |
| portalr's `app` and `admin` | `client`, `ui` |

artifactr's and reflexr's `api` tasks also depend on docplan's and oncall's `image` tasks, since their collections run against those apps. A change to either app then reaches them through `--downstream deep`, which CI uses because `moon ci` defaults to direct dependents only.

### CI and tooling

| Concern | Choice |
|---|---|
| Orchestration | moon. In every job, `moonrepo/setup-toolchain` with `auto-install: true` has proto install moon, uv and Bun at the versions in `.prototools` |
| Keeping `main` green | One required check, `CI` (`re-actors/alls-green`, at v1.3.0 or later), and branches up to date with `main`, both in the ruleset. alls-green counts a skipped job as a failure, so jobs that run only on pull requests go in its `allowed-skips`. No merge queue, since GitHub offers it only to organizations, and `alexnodeland` is a personal account |
| Pull requests | `moon ci --downstream deep`. Python 3.13 and 3.14 run on every pull request, since a public repository's minutes are free |
| `main` and nightly | Every project's `check`, osv-scanner (through `google/osv-scanner-action`) over `uv.lock` and `bun.lock`, and a lychee link check |
| Workflow hardening | actionlint and zizmor, in the hooks and in CI. Every action pinned to a commit SHA with a version comment. `permissions: {}` at the top of each workflow, granted per job, and `persist-credentials: false` |
| Supply chain | OpenSSF Scorecard, weekly. Build-provenance attestations on releases (`actions/attest`). CodeQL (Python, TypeScript). The dependency-review action covers only what GitHub's dependency graph reads, which doesn't include `uv.lock` or `bun.lock`, so osv-scanner's pull request workflow runs on every pull request too |
| Repository security | Secret scanning with push protection, and private vulnerability reporting |
| Test signal | pytest-timeout, and `timeout-minutes` on every job. pytest-randomly. JUnit reports as annotations and job summaries, and moon's run report. Hypothesis and fast-check are allowed dev dependencies everywhere |
| Pull request titles | A lint against the Conventional Commits types and the module scopes, which stay as they are (`mcp`, `scores`, `template`); paths route commits to packages |
| Types | ty (Astral) replaces pyright, configured once at the root. It is beta (0.0.84) and has no strict mode, so every rule is set to `error` (`all = "error"`), and `respect-type-ignore-comments = false`. Its adoption pull request runs both checkers once, reports what pyright strict catches that ty doesn't on this code, and adds `ty: ignore` to the quality test's banned suppressions |
| Hooks | prek replaces pre-commit, with the same `.pre-commit-config.yaml` |
| Releases | release-please replaces git-cliff ([Releases and versioning](#releases-and-versioning)) |
| Dependencies | Renovate replaces Dependabot: `config:best-practices` (SHA-pinned actions, weekly lockfile maintenance), a `minimumReleaseAge` for PyPI as well as npm, its built-in `proto` manager for `.prototools` (a custom manager isn't needed), and PostgreSQL held at major 17 (a regex in `allowedVersions`, since Docker versioning rejects `17.x`). Python ranges use `update-lockfile`, so the libraries' floors stay; stackr's tool floors now move only by hand |
| APIs | Each FastAPI surface's OpenAPI document is committed in its package's `schemas/`, with a drift test like artifactr's `test_schema.py`: artifactr's and reflexr's routers (from a bare app that mounts them), the console service, and later grantr's. Schemathesis runs over the documents against docplan, oncall and the console. portalr's `client` takes its types from the console's document |
| Public Python APIs | `griffe check` against each package's last release tag. A break fails unless the pull request marks it with `!` or `BREAKING CHANGE` |
| Web budgets | knip over the Bun workspace, and size-limit budgets for portalr's `app` and `admin` |

The workflows:

| Workflow | Jobs |
|---|---|
| `ci.yml` | **Check** (Python 3.12): `uv sync --locked --all-packages --all-groups --all-extras`, `bun install --frozen-lockfile`, and `moon ci --downstream deep :check`, with a PostgreSQL 17 service holding one database per library. **Tests** (Python 3.13, 3.14): `moon ci --downstream deep :test`. **Template** and **Smoke**: `moon ci stackr:template` and `moon ci stackr:smoke`, with the matrix values in the environment, which do nothing unless stackr is affected. **Acceptance**: starts docplan, oncall and the console service, then runs `moon ci --downstream deep :api :bdd` and Schemathesis. On pull requests only: **Title**, **Dependency review** and **OSV** (osv-scanner's pull request workflow). **CI**, the one required check |
| `docs.yml` | The family's "one docs build": it builds on every pull request, every push to `main` and by hand, with the concurrency group `docs-${{ github.ref }}` cancelling only on pull requests, and deploys only from `main` |
| `nightly.yml` | On pushes to `main` and nightly: every project's `check`, osv-scanner and lychee |
| `release.yml` | release-please, the builds and their attestations |
| `codeql.yml`, `scorecard.yml` | CodeQL and Scorecard. They arrive in phase 6; the other workflows come with the setup commit |

**prek hooks**, at the root: the hygiene hooks, with `(^|/)CHANGELOG\.md$` excluded from the whitespace fixes and `uv.lock` and `bun.lock` from the large-file check. stackr's `check-json`, `check-executables-have-shebangs` and `detect-private-key` become family-wide. Then `conventional-pre-commit`, ruff, Biome, yamllint and shellcheck (scoped as today), actionlint, zizmor, and the type checker, as the libraries' hooks run pyright today.

### Working with agents

Agents do much of the family's work, so lattice sets them up once, for every package. How to use them belongs in `docs/contributing/agents.md`; this section records the decisions.

| Concern | Settled |
|---|---|
| Instructions | `AGENTS.md` only, with no `CLAUDE.md`: one at the root and one per package. Claude Code reads `AGENTS.md` where a directory has no `CLAUDE.md`, and loads a package's file when it opens a file there. They hold only what the code and docs can't tell an agent, and link to `docs/architecture.md` and the ADRs rather than copying them. `.claude/rules/` holds rules scoped by a `paths:` glob, which load only with a matching file, for migrations, schemas, ADRs, workflows and `.feature` files. A test checks that every path, moon task and ADR number these files mention exists, and holds each file to a line budget |
| Packaging | The family's skills, subagents and hooks form one repo-local plugin, `lattice`, in `tools/claude/`, listed in `.claude-plugin/marketplace.json`. `.claude/settings.json` declares the marketplace and enables the plugin (`extraKnownMarketplaces`, `enabledPlugins`) and sets the permissions. Each skill is a short `SKILL.md`, the reference files it points to, which Claude reads only when needed, and a `claude plugin eval` suite (`evals/<case>/prompt.md` with its graders). Package-specific skills live in `packages/<name>/.claude/skills/` |
| Family skills | issue (start work from one), rfc, adr, pr, review, release, migration, schema-change, adapter (ports and adapters, with the contract suite), cross-package, docs, bdd and retro |
| Hooks | One set, in the plugin's `hooks/hooks.json`; packages differ only through their moon tasks. `PreToolUse` blocks the never-list below. `PostToolUse` formats an edited file and returns lint findings to Claude as `additionalContext`. At `Stop`, Claude can't finish until `moon run :check --affected` passes, guarded by `stop_hook_active`; then a `type: "prompt"` hook, a model acting as judge, checks that the work names its issue and updates the ADRs, RFCs and docs it should. prek and CI run the same moon tasks, so the three layers can't disagree |
| The never-list | Force pushes, pushes to `main`, `--no-verify`, admin merges and bare `git stash`. Suppressions: `# ty: ignore`, `# type: ignore`, `noqa`, `biome-ignore` and `@ts-expect-error`. Edits to generated files (schemas, OpenAPI documents, lockfiles, CHANGELOGs) and to Accepted ADRs. Attribution trailers. Reads of `.env` files |
| Subagents | `reviewer` (the simplicity and idiom review, and the family's rules) and `security-reviewer`, both read-only through their `tools` lists, since plugin subagents ignore `permissionMode`. Editing agents run with `isolation: worktree` |
| Claude on GitHub | `claude-code-action@v1`, with a `CLAUDE_CODE_OAUTH_TOKEN` or API-key secret that the maintainer adds, and the plugin installed through its `plugin_marketplaces` and `plugins` inputs. It reviews every pull request from this repository with the `review` skill and a `REVIEW.md`, on `pull_request` (never `pull_request_target`), skipping forks, which get no secrets anyway. The action already requires write access; the workflow's `if` also limits `@claude` to comments whose `author_association` is `OWNER`. A weekly, headless skill gardener reads the week's review findings, CI failures on agent pull requests, the retro comments, Git AI's acceptance stats and `claude doctor prompt-audit`, then opens an issue and a pull request that closes it, which must pass the skill evals. Minimal permissions, and zizmor-clean |
| GitHub process | YAML issue forms (bug, feature, task, RFC proposal) with a package dropdown. `pkg:<name>` labels on pull requests from `actions/labeler`; issue types exist only for organizations, so labels carry the type. Each RFC gets a tracking issue with a sub-issue per phase, in place of a checkbox Tracking section. A Projects board, "lattice", with Status, Package and Priority fields and the built-in auto-add and auto-close workflows. A required check that each pull request closes an issue, with release-please's and Renovate's exempt |
| Self-improvement | The skill evals gate CI whenever skills, agents or `AGENTS.md` change, and run weekly with `--no-publish`. The `pr` skill ends with a retro comment carrying a marker the gardener finds |
| Chats to changes | Git AI (Apache-2.0) keeps line-level attribution in git notes (`refs/notes/ai`), which are pushed; they name the steering person, whose email is already public in commits. Prompts stay in a local database and are never pushed. It uses no git hooks, so it doesn't clash with prek. `.github/workflows/git-ai.yaml` runs `git-ai ci github run` on merged pull requests (`contents: write`) to keep attribution through squash merges, from a pinned release whose installer checks its checksums. `.git-ai-ignore` covers generated files. On each machine, `allow_repositories` names the maintainer's remotes and `telemetry_oss` is off; note that the installer resets the global git `[trace2]` settings and starts a daemon. Its `ai_accepted` stat still equals `ai_additions`, so acceptance isn't yet a real signal. `git mv` and filter-repo aren't tracked, which is harmless here |
| Later | Each library could publish a plugin for its downstream users, which stackr's generated applications would enable |

### Dev container

One, at the root, replaces the four per-repository ones, and supersedes artifactr ADR-0030 and reflexr ADR-0021.

| Concern | Settled |
|---|---|
| Docker | Docker-in-Docker (`ghcr.io/devcontainers/features/docker-in-docker:4`), for stackr's Compose, Supabase and the smoke tests |
| Egress | A firewall for unattended agent runs, from Anthropic's reference `init-firewall.sh`, which allows GitHub, npm, the Anthropic API and VS Code's endpoints. lattice's adds PyPI, Docker Hub, GHCR and `public.ecr.aws` (Supabase's images). It needs the `NET_ADMIN` and `NET_RAW` capabilities |
| Tools | proto installs moon, uv and Bun from `.prototools`, and `uv python install` provides Python 3.12 to 3.14. Chromium and its dependencies for Playwright. The Claude Code feature (`ghcr.io/anthropics/devcontainer-features/claude-code:1.0`, whose tag pins the install script, not Claude Code's release) and Git AI at a pinned release. `devcontainer-lock.json` pins the features. Renovate bumps them in `devcontainer.json` but can't update the lockfile yet, so its pull requests also run `devcontainer upgrade`, and CI builds with `--frozen-lockfile` |
| Caches | Named volumes for the uv, Bun, moon and proto caches, and for `.venv` |
| Editor | The ty, ruff, Biome, moon, Playwright, Bruno and GitHub Actions extensions; format on save, and ty as the language server. Forwarded ports carry labels |
| Secrets | Codespaces secrets in a codespace, and `remoteEnv` (`${localEnv:…}`) locally; never baked into the image |
| Image | CI builds it with `devcontainers/ci`, checks that the tools resolve and `uv sync --locked` works, and publishes it to GHCR. Codespaces prebuilds sit on top, a repository setting the maintainer approved |

The setup commit brings a basic root dev container, since the old ones break with the new layout. The firewall, the prebuilt image and Codespaces come in phase 7.

### Docs

**One site, one build, one `mkdocs.yml`.**

- `docs_dir` is `docs`. The family's pages sit at its root, and each package's at `docs/<package>/`, with its own `.nav.yml`. Zensical implements awesome-nav natively, so each folder's `.nav.yml` sets its section's order.
- The setup commit runs `git mv packages/<name>/docs docs/<name>`, and `git log --follow` keeps each page's history.
- There are no per-package `mkdocs.yml` files, no shared base configuration, no composing script and no staged tree. Keeping the pages in the packages would need all of those: Zensical has no monorepo plugin, `docs_dir` is one directory, and it doesn't follow symlinks.
- One build resolves cross-references between packages, so mkdocstrings needs no sibling inventories. artifactr's and reflexr's evalr inventory goes. Every member is installed in the root environment, so mkdocstrings should need no `paths`; phase 1 confirms it.
- lattice has one `CONTRIBUTING.md`, code of conduct, security policy and license, so those pages exist once, at the family level. They absorb what was package-specific: each package's commands in CONTRIBUTING, artifactr's tenant-isolation scope in SECURITY ([artifactr ADR-0011][a-adr-0011]), and the packages in the bug report's "Package" list. Each package keeps its changelog page, included from `packages/<name>/CHANGELOG.md`.
- **The brand.** The header mark, favicon and palette are lattice's, and each section's home opens with its package's banner. Marks for lattice, grantr and portalr are for a later brand ADR.

**The old sites** at `artifactr.`, `reflexr.`, `evalr.` and `stackr.alexnodeland.com` keep serving the old pages until they are retired separately (D1). `relayr.`, `portalr.` and `grantr.` have Pages domains set but no DNS records. A CNAME record left pointing at a deleted repository's Pages can be taken over, so a record goes when its repository does, and verifying the domain comes first ([the day](#migration), step 0).

### Releases and versioning

- **Versions are per package,** in each `pyproject.toml` as today.
- **release-please** (`googleapis/release-please-action` v5) runs in manifest mode. `release-please-config.json` lists each package's path with the `python` release type and a `package-name`, which gives the tags their component; `.release-please-manifest.json` holds the versions. It opens one release pull request, and merging it tags `<package>-v<version>`, updates each package's `CHANGELOG.md` and creates a GitHub release per package. Its `bootstrap-sha` is the import, so it never reads the old history.
- **The release pull request updates `uv.lock` too.** uv records each member's version in the lock, so a bump alone makes `uv sync --locked` fail (verified). Each package lists the lock as a `toml` extra file, with the JSONPath `$.package[?(@.name.value=='<distribution>')].version`.
- **Module scopes stay.** release-please routes commits to packages by path, and a lockstep pull request that touches two packages appears in both changelogs.
- **The docs lose the live "Unreleased" section** that git-cliff regenerated on every build. The open release pull request shows what is pending instead.
- **Tags are `<package>-v<version>`,** and the import renames the old tags the same way (artifactr's `v0.1.0` becomes `artifactr-v0.1.0`). This matters: Copier takes the latest tag that parses as a PEP 440 version as the template's release, and a bare `v0.1.0` does. Prefixed tags don't.
- **The changelogs' history is generated once.** The setup commit runs git-cliff from each package's directory, which scopes it to that directory, with `--tag-pattern "<package>-v.*"`. artifactr's `cliff.toml` skips eight prototype commits by SHA, so those SHAs are first mapped through filter-repo's `commit-map`. After that, git-cliff and every `cliff.toml` retire.
- **`release.yml`** builds each released package alone (`uv build --package <name> --no-sources`), attaches the wheel and sdist to its release, and attests their provenance. PyPI publishing is a later job in the same workflow, with trusted publishing, when [artifactr #23][a-23] decides.
- **Dashboards come from the checkout.** stackr provisions the libraries' Grafana dashboards from `packages/*/deploy/grafana/dashboards`. `fetch-dashboards`, its pins in `versions.env`, the libraries' `release-assets.yml`, and dashboards on releases all retire.

### stackr's template, from inside lattice

**Finding it.** Copier reads `copier.yml` at the repository's root, and `_subdirectory` is the supported way to keep the template's files elsewhere. So lattice's root `copier.yml` is a pointer:

```yaml
---
!include packages/stackr/copier.yml
---
_subdirectory: packages/stackr/template
```

Copier supports `!include`, and a later document's settings replace an earlier one's (tested with Copier 9.18.2). `uvx copier copy gh:alexnodeland/lattice my-app` works as `gh:alexnodeland/stackr` does today. With only prefixed tags, Copier finds no release and takes `HEAD`, as it does today.

**Pinning (D4).** A generated application pins every library it uses from lattice, at the commit the template was rendered from, which Copier provides as `_copier_conf.vcs_ref_hash`:

```toml
[tool.uv.sources]
artifactr-ai = { git = "https://github.com/alexnodeland/lattice", subdirectory = "packages/artifactr", rev = "<the rendered commit>" }
reflexr = { git = "https://github.com/alexnodeland/lattice", subdirectory = "packages/reflexr", rev = "<the rendered commit>" }
evalr = { git = "https://github.com/alexnodeland/lattice", subdirectory = "packages/evalr", rev = "<the rendered commit>" }
```

- **ADR-0013's evalr special case goes.** uv lowers the libraries' own `evalr = { workspace = true }` to the same repository and commit (verified), and the application's own line names that same commit, so the two can't disagree.
- **Applications get the combination CI tested.** `copier update` moves the template and the libraries together, and `bump-libraries` retires.
- **Two quirks.** An application's `_commit` becomes `git describe --tags` of the nearest package tag, such as `evalr-v0.2.0-1-gf4e1841`. That is harmless for updates, but confusing. And an application rendered from a pull request's branch stays installable after a squash merge, since GitHub keeps `refs/pull/<n>/head`.
- **Tested in the same pull request.** The Template and Smoke jobs render the template with path sources to the checkout's packages (a hidden answer, `libraries_path`). A library change and the template's adaptation then land together.
- **stackr's scripts render from lattice's root.** From `packages/stackr`, Copier would see a directory that isn't a repository's root, and `vcs_ref_hash` would be None. So `validate` and `check-template` render from the root. `docs-reference` regenerates from the Makefile, the root `copier.yml` and the trimmed `versions.env`.
- **Existing applications** change `_src_path` to `gh:alexnodeland/lattice`, and map `_commit` through filter-repo's commit map. RFC-0002's product repository isn't generated yet, so there may be none.

### Migration

**One principle orders the work.** The import and the setup commit change only what the move forces, or what would otherwise be written twice: the docs' placement, shared configuration, Renovate instead of `dependabot.yml`, prek, release-please's configuration, and the workflows. Anything that can change test outcomes lands in lattice afterwards, each as its own pull request (phase 6).

**History,** for artifactr, reflexr, evalr and stackr, and for relayr's `chore/foundation` branch (fd54088), each in a fresh clone:

```sh
git filter-repo --to-subdirectory-filter packages/<name> \
  --tag-rename '':'<name>-' \
  --replace-message messages-<repo>.txt
```

- **The message rules,** in order: `regex:\b(artifactr|reflexr|evalr|stackr|relayr) ?#(\d+)==>alexnodeland/\1#\2`, then `regex:(?<![\w/])#(\d+)==>alexnodeland/<repo>#\1`. The first catches prose such as "reflexr #90" or "reflexr#90"; the second catches every bare reference, such as `Closes #63` and `(#64)`. About 41 bare references sit in the commit bodies, beyond the squash titles' `(#N)`.
- **Merged as unrelated histories,** one repository after another.
- **grantr and portalr aren't imported.** Each holds one initial commit with a README and a license, and the setup commit copies the README's content.
- **The setup commit** moves the docs, docplan and oncall; changes sibling sources to `{ workspace = true }`; replaces the per-repository lockfiles, workflows, hooks, tool configuration, quality tests, dev containers and project pages with the root's; generates the changelogs' history; points docplan's and oncall's images at the root context; and retires the dashboard releases.
- **Docker builds** start from lattice's root, since the images need the root `uv.lock`. Each image has its own `Dockerfile.dockerignore`, which lets in the members' `pyproject.toml` files, `uv.lock` and the sources it installs. artifactr's git-in-the-image workaround (ADR-0044) goes, since nothing installs from git.
- **A basic dev container** at the root replaces the four ([Dev container](#dev-container)).

**Issues.**

- The 12 open issues move with `gh issue transfer <n> alexnodeland/lattice`: artifactr 3, reflexr 3, stackr 6. Labels and milestones carry over only if they already exist in lattice, so the labels are created first. Old issue URLs redirect.
- The transfer script rewrites bare `#N` with the same two rules, in the bodies and the comments.
- The history is pushed before the transfers. So no issue exists in lattice when the history lands, and a closing keyword that the rewrite missed can't close one.
- Closed issues and pull requests stay in the old repositories.

**The day,** with the loop paused. It takes about a day:

| Step | What happens | Done when |
|---|---|---|
| 0. Domain | The maintainer verifies `alexnodeland.com` for Pages in the account settings (a TXT record) | GitHub shows the domain verified |
| 1. Freeze | Pause the loop, and merge nothing in the old repositories | Their `main`s are final |
| 2. Import | Run the rehearsed script on fresh clones, create `alexnodeland/lattice`, and push `main` and the tags directly | lattice's history shows every package's commits under its directory |
| 3. Settings | The siblings' `main` ruleset, with the required `CI` check and up-to-date branches. Squash-only merges. Secret scanning with push protection, and private vulnerability reporting. The labels | A direct push to `main` is refused |
| 4. Pages | Pages builds from Actions, with `lattice.alexnodeland.com`. Then the maintainer adds the `lattice` CNAME, and HTTPS is enforced | The site is live |
| 5. Verify | A trivial pull request through the ruleset | CI is green, and the site has every section |
| 6. Issues | Transfer the open issues | Old issue URLs land in lattice |
| 7. Resume | Update the links (READMEs, stackr's docs, the packages' `pyproject.toml` URLs), and restart the loop in lattice | New work opens against lattice |

The script is rehearsed first in a local directory, until `uv sync --locked`, `moon run :check` and the docs build pass there. The day then only repeats it.

**Each package records the move in its own ADRs,** as the first pull requests in lattice:

| Package | ADRs that change |
|---|---|
| artifactr | 0023, 0026, 0050 (docs); 0024 (docplan's place); 0044 (evalr's pin); 0041 (dashboards on releases); 0032 (stackr in its own repository); 0030 (Compose and dev containers); 0040 (stackr's network); 0015 (quality gates) |
| reflexr | 0032, 0033, 0046 (docs); 0015 (oncall's place); 0020 (evalr's pin); 0038 (dashboards on releases); 0023 (stackr in its own repository); 0021 (Compose and dev containers); 0037 (stackr's network); 0013 (quality gates) |
| evalr | 0010, 0013 (docs); 0005 (quality gates) |
| stackr | 0012, 0014 (docs); 0013 (the pins) |
| relayr | 0001 (its own repository); 0011 (docs); 0012 (the pins); 0009 (quality gates) |

## Decisions

The maintainer settled these on 2026-09-30.

| Decision | Settled |
|---|---|
| Name and packages | `alexnodeland/lattice`, a new public repository; only the monorepo drops the family's "-r". The packages keep their names: artifactr (distribution `artifactr-ai`), reflexr, evalr, stackr, relayr (distribution `relayr-ai`), grantr and portalr. `stackr` is taken on PyPI too, but stackr ships no wheel |
| Tooling | moon over a uv workspace and a Bun workspace. moon was chosen over plain workspaces with a justfile, and over Pants, which has no Bun support. The rest is in [CI and tooling](#ci-and-tooling) |
| Repository settings | The siblings' `main` ruleset, applied after the initial import, which is pushed directly, plus the required `CI` check and up-to-date branches. Pages builds from Actions, with the custom domain. Secret scanning with push protection, and private vulnerability reporting |
| relayr, grantr and portalr | The maintainer removes or archives these repositories. This RFC moves only their content, including relayr's `chore/foundation` branch |
| D1: the four old repositories | Left alone: no pointer README, no redirect site, no archiving, and Actions stay as they are. The maintainer deals with them later. Their sites keep serving until then |
| D2: Makefiles | A thin root Makefile with `install`, and `check`, which calls moon. stackr keeps its Makefile. The libraries' other targets become moon tasks with `runInCI: false` and `cache: false` |
| D3: moon's Python toolchain | Off until it is stable. Python tasks are plain `uv run` commands with `/uv.lock` as an input |
| D4: the template's pins | The commit the template is rendered from (`_copier_conf.vcs_ref_hash`) |
| D5: Bruno collections | Per package, in `packages/<name>/bruno/`, run by each project's `api` task |
| Docs placement | `docs/<package>/` at the root, with one `mkdocs.yml` and a `.nav.yml` per folder |
| Dashboards | Provisioned from the checkout; dashboard releases retire |
| Undeclared imports | deptry over `src/` |
| Tool configuration | Shared at the root: ruff now, and ty when it replaces pyright |
| Agents and the dev container | As recorded in [Working with agents](#working-with-agents) and [Dev container](#dev-container) |

## Phases

| Phase | Deliverable | Exit criteria |
|---|---|---|
| 1. Rehearsal | The import script and the setup commit, run locally against fresh clones | `uv sync --locked`, `bun install --frozen-lockfile`, `moon run :check` and the docs build pass, and `git log --follow` shows a file's history from its old repository |
| 2. The day | Steps 0 to 7 of [Migration](#migration) | lattice's CI is green through the ruleset, and the site is live with every section |
| 3. Package ADRs | The ADRs each package supersedes or amends, and the family's `docs/architecture.md` | Each package's docs describe lattice, not its old repository |
| 4. The template in lattice | Pinning by the rendered commit, path sources in CI, `bump-libraries` retired | A pull request that changes a library and the template together passes the Template and Smoke jobs |
| 5. Acceptance tests | The OpenAPI documents and their drift tests, the Bruno collections for artifactr's and reflexr's REST surfaces, and the Acceptance job. portalr's collection and its `bdd` task come with the portal RFC | The Acceptance job runs `bru run` against a started stack |
| 6. Test signal and hardening | One pull request each: ty, pytest-randomly, timeouts, Schemathesis, CodeQL, `griffe check` and Scorecard | Each lands green on its own, with anything it finds fixed or recorded |
| 7. Agents and process | `AGENTS.md`, the `lattice` plugin (skills, subagents, hooks, evals), the Claude and Git AI workflows, the issue forms, labels and board, and the dev container's firewall, prebuilt image and Codespaces. Each is a pull request linked to its sub-issue | An agent in the dev container starts from an issue and ends with a pull request that passes the Stop hook, the evals and review |

## Drawbacks

- **One resolution couples upgrades.** A third-party upgrade has to pass every package, and one package can't hold a dependency back alone.
- **A broken `main` blocks everyone.** Before, a red CI in one repository blocked only that one.
- **New tools at once:** moon, ty (still beta), prek, release-please and Renovate. Sequencing keeps each change that can move test results in its own pull request.
- **Numbers restart.** Issues and pull requests in lattice start from #1, beside the rewritten links into the old repositories.
- **A package's pages leave its directory,** as the price of one plain docs build.
- **Copier's advice is bent.** Its documentation recommends one template per repository, because tags are shared. Prefixed tags keep the template's apart.
- **A bigger checkout** for anyone who wants one package. Downstream installs from git fetch the whole repository.

## Alternatives

- **Staying multi-repository.** The costs in [Motivation](#motivation) continue, and grow with three new repositories.
- **A shared package for the verbatim helpers,** with the repositories kept apart. It moves one symptom and keeps the pins. It is also the kernel that reflexr ADR-0003 deferred.
- **Submodules or subtrees in one umbrella repository.** They keep separate histories and pins, which is the problem this RFC solves.

## Unresolved questions

- **portalr's npm names,** if `client` and `ui` are ever published. `@portalr/*` needs the npm organization, or they go under another scope.
- **Template releases.** With prefixed tags, Copier always follows `HEAD`. If stackr ever wants releases that Copier can see, it would need bare PEP 440 tags reserved for the template.
- **One mkdocstrings configuration for the whole site.** artifactr's and reflexr's Griffe extension for Sphinx roles would apply to every package, including evalr's and relayr's Markdown docstrings. It should be harmless; phase 1 checks it.
- **What ty misses.** Its adoption pull request reports what pyright strict catches that ty doesn't, and the family decides then whether any gap needs a stopgap.

## Tracking

In lattice, this list becomes a tracking issue with a sub-issue per phase (phase 7).

- [x] Sign-off on the decisions (2026-09-30)
- [x] Phase 1: rehearsal (2026-09-30)
- [x] Phase 2: the day (2026-09-30)
- [ ] Phase 3: package ADRs and the family architecture
- [ ] Phase 4: the template in lattice
- [ ] Phase 5: acceptance tests
- [ ] Phase 6: test signal and hardening
- [ ] Phase 7: agents and process

### What the rehearsal settled

Phase 1 rehearsed the move from fresh clones, and an independent review checked the result. The design above stands as accepted. Where the rehearsal found it wrong or silent, lattice does what follows instead, and phase 3's ADRs record each decision.

- **The import.**
  - The first message rule starts with `(?<![\w/])`, not `\b`. Two messages already said `alexnodeland/evalr#17`, which `\b` would have rewritten a second time.
  - The import pins all five sources, not only relayr's.
- **The setup commits.**
  - The setup is a series of commits, one concern each. One of them is a `style:` commit that only sorts the imports naming a sibling, and `.git-blame-ignore-revs` names it.
  - One artifactr test was added: artifactr's MCP app was covered only by docplan's tests.
  - grantr's and portalr's READMEs live in lattice's README until their code arrives.
- **One resolution.** evalr's DSPy runs on litellm 1.83.0, because every later litellm pins `openai<3`, which `pydantic-ai-slim[openai]` can't share. `osv-scanner.toml` records litellm's 13 advisories (all in its proxy server, which lattice never runs), diskcache's unfixed one, and a name collision with an unrelated PyPI package called `oncall`.
- **Declared imports.** Each package declares the modules deptry found it importing without declaring them: jsonpointer, pydantic-core, annotated-types, huggingface-hub, starlette and httpx2. Each floor narrows no install. deptry is part of `check`.
- **Tool configuration.** Each package keeps its whole pytest and coverage configuration, since neither tool reads a parent directory's.
- **moon.**
  - `moon ci --downstream deep` doesn't reach dependents' tasks, and `moon query projects --affected` misses root files such as `uv.lock`. So CI runs `scripts/affected.py`, which adds every dependent from the project graph.
  - docplan depends on evalr too.
  - stackr is `language: bash`, `layer: tool`.
  - There is no `.moon/toolchains.yml` until portalr brings Bun.
  - `.prototools` sets `detect-strategy = "only-prototools"`, so uv alone installs Python.
  - `build` runs from each package's directory with `--out-dir dist`.
- **CI.**
  - `ci.yml` runs on pull requests only, with an Images job; `nightly.yml` covers `main`.
  - Title is its own workflow and a second required check, since CI never reruns when a title is edited. It checks the Conventional Commits types, not the scopes.
  - A `.prekignore` keeps prek from running the template's own hook configuration.
  - The repository's dependency graph is on, since dependency review needs it.
  - Phase 6's timeouts landed on the day ([#4](https://github.com/alexnodeland/lattice/pull/4)): every test fails after a minute, and every job at a limit. docplan's tests hung in CI's Check job three times in five runs, and never locally.
  - The Template task runs the generated application with the checkout's `uv`, since proto's shim chooses no version outside lattice, and only when stackr changes ([#3](https://github.com/alexnodeland/lattice/pull/3)). [#18](https://github.com/alexnodeland/lattice/issues/18) tracks the PostgreSQL variables that still make every pull request run artifactr's and reflexr's tests.
- **Renovate** runs from lattice's own Actions (`renovate.yml`), not as Mend's hosted app, and its `pre-commit` manager is on.
- **Docs.**
  - Each folder's `.nav.yml` applies only with `awesome-nav` listed under `plugins`.
  - Each package's README uses absolute links, since it is also the package's PyPI page.
  - relayr's section starts at its decisions until relayr writes a landing page.
- **Images.** Each `Dockerfile.dockerignore` also lets in every member's `pyproject.toml`, and the installed members' `README.md` and `LICENSE`.
- **Releases.**
  - The manifest holds each package's last tagged version, or `0.0.0`, so a first release is 0.1.0. `bump-minor-pre-major` is on.
  - Each changelog keeps the history before the import under "Before lattice". release-please inserts releases above it, and never reads that far back.
  - release-please and Renovate act as one GitHub App, `alexnodeland-lattice`, with a token narrowed for each workflow.

[a-23]: https://github.com/alexnodeland/artifactr/issues/23
[a-43]: https://github.com/alexnodeland/artifactr/pull/43
[a-56]: https://github.com/alexnodeland/artifactr/pull/56
[a-59]: https://github.com/alexnodeland/artifactr/pull/59
[a-64]: https://github.com/alexnodeland/artifactr/pull/64
[a-67]: https://github.com/alexnodeland/artifactr/pull/67
[a-69]: https://github.com/alexnodeland/artifactr/pull/69
[a-70]: https://github.com/alexnodeland/artifactr/pull/70
[a-71]: https://github.com/alexnodeland/artifactr/pull/71
[a-adr-0011]: https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0011-workspace-scoped-artifacts-and-tenant-handles.md
[a-adr-0050]: https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0050-one-docs-build.md
[e-27]: https://github.com/alexnodeland/evalr/pull/27
[e-34]: https://github.com/alexnodeland/evalr/pull/34
[e-adr-0013]: https://github.com/alexnodeland/evalr/blob/main/docs/adr/0013-docstrings-in-markdown-and-one-docs-build.md
[r-55]: https://github.com/alexnodeland/reflexr/pull/55
[r-70]: https://github.com/alexnodeland/reflexr/pull/70
[r-73]: https://github.com/alexnodeland/reflexr/pull/73
[r-76]: https://github.com/alexnodeland/reflexr/pull/76
[r-79]: https://github.com/alexnodeland/reflexr/pull/79
[r-80]: https://github.com/alexnodeland/reflexr/pull/80
[r-81]: https://github.com/alexnodeland/reflexr/pull/81
[r-85]: https://github.com/alexnodeland/reflexr/pull/85
[r-90]: https://github.com/alexnodeland/reflexr/pull/90
[r-adr-0003]: https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0003-independent-sibling-of-artifactr.md
[r-adr-0046]: https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0046-one-docs-build.md
[s-36]: https://github.com/alexnodeland/stackr/pull/36
[s-38]: https://github.com/alexnodeland/stackr/pull/38
[s-40]: https://github.com/alexnodeland/stackr/pull/40
[uv-13298]: https://github.com/astral-sh/uv/issues/13298
[uv-16640]: https://github.com/astral-sh/uv/issues/16640
