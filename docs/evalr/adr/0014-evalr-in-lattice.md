# ADR-0014: evalr in lattice

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

Amends [ADR-0004](0004-trunk-based-development-with-rfcs-and-adrs.md), how the changelog is written; [ADR-0005](0005-quality-gates-and-license.md), where the gates run; and [ADR-0011](0011-scores-shared-with-the-libraries.md), how the libraries get evalr.

## Context

evalr was a repository of its own, with its own lock, CI, hooks and changelog, and artifactr and reflexr each pinned it by git revision, in lockstep, since uv can't lock two revisions of one package. On 2026-09-30 it moved, with its history, into lattice, the family's one repository, as [stackr RFC-0003](../../stackr/rfcs/0003-one-repository-lattice.md) designed. Downstream, evalr stays what it was: its name, version, dependencies, extras, tests and gates. What changed is where it is built, checked and released, and how its dependents get it.

## Decision

- **evalr is `packages/evalr`, a member of lattice's uv workspace.** Its `pyproject.toml` keeps its metadata and its pytest and coverage configuration; ruff is configured once, at lattice's root, and pyright stays evalr's own until ty replaces it.
- **The libraries take evalr from the workspace** (ADR-0011's "the libraries pin it by git revision"). artifactr and reflexr require it by a range, docplan through its `[dspy]` extra, and `[tool.uv.sources]` takes it from the workspace, so they always run against the evalr in the same commit. A built wheel carries the range, and no path.
- **lattice's CI runs the gates** (ADR-0005, and ADR-0004's "CI gates every merge"). The gates stand, and so do no network in tests and the MIT license. CI runs them on every pull request that affects evalr, on Python 3.12 and on 3.13 and 3.14, with the checks of every project that depends on it ([lattice ADR-0002](../../adr/0002-ci-runs-every-affected-project-and-its-dependents.md)), and `nightly.yml` runs them on `main`. `uv sync --locked` checks lattice's one `uv.lock`. `check` now also installs evalr's wheel outside the workspace and imports every module, and runs deptry over `src/`. The test that forbids inline suppressions is lattice's, over every package, and a test that runs for a minute fails ([lattice ADR-0007](../../adr/0007-a-timeout-on-every-test-and-every-job.md)).
- **release-please writes the changelog and cuts the releases** (ADR-0004's git-cliff). The tags are `evalr-v<version>`, the first release is 0.1.0, and only features, fixes, performance changes and reverts release ([lattice ADR-0006](../../adr/0006-release-please-first-versions-pre-1-0-bumps-and-what-releases.md)). `CHANGELOG.md` keeps the history before lattice under "Before lattice". Squash merges with Conventional Commit titles stand; the Title check ([lattice ADR-0003](../../adr/0003-two-required-checks-ci-and-title.md)) and the `commit-msg` hook, which prek now runs, check them.

RFC-0003 weighed the alternatives to moving: staying in a repository of its own, a shared package, and submodules.

## Consequences

- Easier: a change to evalr runs the libraries' tests in the same pull request, and the libraries' pins no longer move in lockstep.
- Easier: every change checks evalr's wheel as a user installs it.
- Harder: evalr's third-party dependencies resolve with every sibling's, in one lock. DSPy's litellm is held at 1.83.0 for that reason ([lattice ADR-0008](../../adr/0008-one-resolution-litellm-held-at-1-83-0.md)).
- Harder: in one environment the libraries are importable from evalr's code, so its layering test, which forbids importing them by name, and deptry are what keep evalr independent of them.
