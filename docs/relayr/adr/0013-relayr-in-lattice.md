# ADR-0013: relayr in lattice

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

Supersedes [ADR-0012](0012-the-libraries-pinned-by-git-revision.md), and [ADR-0001](0001-relayr-its-own-repository-and-package.md)'s own repository. Amends [ADR-0008](0008-trunk-based-development-with-rfcs-and-adrs.md), how the changelog is written, and [ADR-0009](0009-quality-gates.md), where the gates run.

## Context

ADR-0001 made relayr a sibling repository and package, and ADR-0012 pinned artifactr and reflexr in it by git revision, each pin moving in its own pull request. Its foundation, on a branch, had copies of the siblings' workflows, hooks, Makefile and changelog configuration. On 2026-09-30 that branch moved, with its history, into lattice, the family's one repository, as [stackr RFC-0003](../../stackr/rfcs/0003-one-repository-lattice.md) designed, before relayr's repository had merged anything.

## Decision

- **relayr is `packages/relayr`, a package in lattice** (ADR-0001's repository). What ADR-0001 decided about the package stands: what it holds, that it uses the libraries' public APIs only, and its name. It is distributed as `relayr-ai`, since `relayr` is taken on PyPI, and still imported as `relayr`. How stackr's template wires it in is RFC-0003's phase 4.
- **artifactr and reflexr come from the workspace** (ADR-0012). `pyproject.toml` requires `artifactr-ai` and `reflexr` by a range, and `[tool.uv.sources]` takes them from lattice's workspace, so relayr always runs against the libraries in the same commit. There are no pins to move: CI checks relayr on every pull request that changes either library, or evalr beneath them ([lattice ADR-0002](../../adr/0002-ci-runs-every-affected-project-and-its-dependents.md)). relayr still requires no extra that needs evalr. A built wheel carries the ranges, and no path.
- **lattice's CI runs the gates** (ADR-0009, and ADR-0008's "CI gates every merge"). The gates stand, on Python 3.12 with PostgreSQL and on 3.13 and 3.14, and `nightly.yml` runs them on `main`. `uv sync --locked` checks lattice's one `uv.lock`. `check` also installs relayr's wheel, with artifactr's and reflexr's, outside the workspace and imports every module, and runs deptry over `src/`. The test that forbids inline suppressions is lattice's, over every package; a test that runs for a minute fails ([lattice ADR-0007](../../adr/0007-a-timeout-on-every-test-and-every-job.md)); and the site's strict build is lattice's ([ADR-0014](0014-one-site-for-the-family.md)).
- **release-please writes the changelog and cuts the releases** (ADR-0008's git-cliff). The tags are `relayr-v<version>`, the first release is 0.1.0, and only features, fixes, performance changes and reverts release ([lattice ADR-0006](../../adr/0006-release-please-first-versions-pre-1-0-bumps-and-what-releases.md)). Squash merges with Conventional Commit titles stand; the Title check ([lattice ADR-0003](../../adr/0003-ci-on-pull-requests-nightly-on-main-and-a-required-title-check.md)) and the `commit-msg` hook, which prek now runs, check them.

## Consequences

- Easier: a change to a library and relayr's adaptation to it land in one pull request, tested together, and a change to either library shows at once whether relayr still passes.
- Harder: relayr's third-party dependencies resolve with every sibling's, in one lock ([lattice ADR-0008](../../adr/0008-one-resolution-litellm-held-at-1-83-0.md)).
- Harder: a library's pull request that breaks relayr fails, so the library's author fixes relayr in the same pull request, where a pin used to let relayr follow later.
