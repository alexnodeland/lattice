# ADR-0006: release-please: first versions, pre-1.0 bumps, and what releases

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

[RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#releases-and-versioning) replaced git-cliff with release-please in manifest mode: one release pull request for every package with unreleased changes, tags `<package>-v<version>`, each package's `CHANGELOG.md`, and `uv.lock` updated with the versions. Its `bootstrap-sha` is the import, so it never reads the history before lattice. Four things were left open, which the setup and the first release pull request ([#19](https://github.com/alexnodeland/lattice/pull/19)) settled:

- **The versions in the manifest.** artifactr alone has been released, as 0.1.0, whose tag the import renamed `artifactr-v0.1.0`. The other packages' `pyproject.toml` say `0.1.0.dev0`, which release-please reads as 0.1.0, so a pyproject version can't stand for "never released".
- **Breaking changes before 1.0.** The family marks them with `!`, and has bumped the minor version for them while below 1.0. release-please's default would release 1.0.0.
- **The history before the import.** git-cliff wrote each changelog up to the import, and release-please reads nothing before it.
- **What cuts a release.** release-please's default changelog sections count `docs` as releasable, so #19 would have released all five packages, with the move's `docs:` commits as their only notes.

## Decision

- **The manifest holds each package's last released version:** its newest `<package>-v*` tag's, or `0.0.0` for a package never released, whose first release is then 0.1.0. release-please finds artifactr's by its tag, so no GitHub Release was made in lattice for it.
- **`bump-minor-pre-major` is on,** so a breaking change bumps the minor version before 1.0.
- **Each changelog keeps its history under "Before lattice".** The setup ran git-cliff once more, in each package's rewritten history; what no release carries is headed "Before lattice", with no compare link. release-please inserts each release above it. git-cliff and every `cliff.toml` then retired.
- **Only `feat`, `fix`, `perf` and `revert` cut a release** ([#21](https://github.com/alexnodeland/lattice/pull/21)), as do breaking changes of any type, in the sections Features, Bug Fixes, Performance Improvements and Reverts. `docs`, `refactor`, `test`, `build`, `ci`, `style` and `chore` are hidden sections: release-please can't list a type in the notes without letting it release, so they appear in no release notes, and stay in the history and the pull requests.
- **The release pull request stays open until the maintainer wants a release.** Merging it tags and releases what it lists.

## Options considered

| Setting | Chosen | Otherwise |
|---|---|---|
| An unreleased package's version in the manifest | `0.0.0`, so its first release is 0.1.0 | Its pyproject's, read as 0.1.0: a first release of 0.1.1 or 0.2.0, as if 0.1.0 were out |
| A breaking change before 1.0 | A minor bump, as the family always has | 1.0.0 |
| The history before the import | Kept, under "Before lattice" | Only what release-please releases, from the import on |
| Releasable types | `feat`, `fix`, `perf`, `revert`, and breaking changes | These, and `docs` |

## Consequences

- Easier: a release pull request lists the changes a package's users see, and a package whose only changes are documentation, tests or builds doesn't release.
- Easier: each changelog reads from the package's first commit, across the move.
- Harder: a change must be typed `feat`, `fix`, `perf` or `revert` to release. A `build:` change to a package's dependency ranges releases nothing on its own; if users need it, it is a `fix`.
- Revisit: publishing to PyPI ([#7](https://github.com/alexnodeland/lattice/issues/7)) adds a job to `release.yml`; nothing here changes.
