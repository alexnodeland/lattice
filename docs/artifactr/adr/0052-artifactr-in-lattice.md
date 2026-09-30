# ADR-0052: artifactr in lattice

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

Amends [ADR-0014](0014-trunk-based-development-with-rfcs-and-adrs.md), how the changelog is written; [ADR-0015](0015-quality-gates.md), where the gates run; [ADR-0024](0024-reference-implementation-as-a-workspace-member.md), where docplan lives; and [ADR-0032](0032-libraries-and-the-stackr-template.md), where stackr lives. Supersedes [ADR-0044](0044-the-evalr-adapter.md)'s pin of evalr.

## Context

artifactr was a repository of its own, with its own lock, CI, hooks, Makefile and releases. On 2026-09-30 it moved, with its history, into lattice, the family's one repository, as [stackr RFC-0003](../../stackr/rfcs/0003-one-repository-lattice.md) designed. Downstream, artifactr stays what it was: `artifactr-ai`, with its version, dependencies, extras, tests and gates. What changed is where it is built, checked and released, and with it the parts of five records that named its own repository or stackr's.

## Decision

- **artifactr is `packages/artifactr`, a member of lattice's uv workspace.** Its `pyproject.toml` keeps its metadata and its pytest and coverage configuration; ruff is configured once, at lattice's root, and pyright stays artifactr's own until ty replaces it.
- **stackr is `packages/stackr`, beside artifactr** (ADR-0032's "in its own repository"). ADR-0032's division of work stands: artifactr is a library, and the stack and the application template are stackr's.
- **evalr comes from the workspace** (ADR-0044's last bullet, and its amendment). The `[langfuse]` and `[evals]` extras require evalr by a range, and `[tool.uv.sources]` takes it from the workspace, so artifactr always runs against the evalr in the same commit. The git pin, and its pull requests, are gone; a built wheel carries the range, and no path.
- **docplan is `examples/docplan`** (ADR-0024), a member of lattice's workspace, since uv refuses a member inside another. It is a project of its own, with its own tests and 100% gate, and artifactr's layering test still holds it to the public API.
- **lattice's CI runs the gates** (ADR-0015, and ADR-0014's "CI gates every merge"). The gates stand. CI runs them on every pull request that affects artifactr or anything it depends on ([lattice ADR-0002](../../adr/0002-ci-runs-every-affected-project-and-its-dependents.md)), on Python 3.12 with PostgreSQL and on 3.13 and 3.14, and `nightly.yml` runs them on `main`. `uv sync --locked` checks lattice's one `uv.lock`. `check` now also installs artifactr's wheel outside the workspace and imports every module, and runs deptry over `src/`. The test that forbids inline suppressions is lattice's, over every package, and a test that runs for a minute fails ([lattice ADR-0007](../../adr/0007-a-timeout-on-every-test-and-every-job.md)).
- **release-please writes the changelog and cuts the releases** (ADR-0014's git-cliff). The tags are `artifactr-v<version>`, as the import renamed `v0.1.0`, and only features, fixes, performance changes and reverts release ([lattice ADR-0006](../../adr/0006-release-please-first-versions-pre-1-0-bumps-and-what-releases.md)). `CHANGELOG.md` keeps the history before lattice under "Before lattice". Squash merges with Conventional Commit titles stand; the Title check ([lattice ADR-0003](../../adr/0003-ci-on-pull-requests-nightly-on-main-and-a-required-title-check.md)) and the `commit-msg` hook, which prek now runs, check them.
- **The Makefile's targets are moon tasks** (RFC-0003, D2): `moon run artifactr:schema`, and likewise `dashboards`, `pg-up`, `pg-down`, `app-up` and `test-pg`. `make check`, at lattice's root, runs every project's checks. A record that names a `make` target means its task.

RFC-0003 weighed the alternatives to moving: staying in a repository of its own, a shared package, and submodules.

## Consequences

- Easier: a change to artifactr and evalr, or to artifactr and docplan, lands in one pull request, tested together, and no pin moves in lockstep.
- Easier: every change checks artifactr's wheel as a user installs it.
- Harder: artifactr's third-party dependencies resolve with every sibling's, in one lock ([lattice ADR-0008](../../adr/0008-one-resolution-litellm-held-at-1-83-0.md)).
- Until artifactr is on PyPI ([lattice#7](https://github.com/alexnodeland/lattice/issues/7)), it installs from its tag, in lattice's `packages/artifactr`.
