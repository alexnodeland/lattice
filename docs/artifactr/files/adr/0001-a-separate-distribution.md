# ADR-0001: A separate distribution

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Records [lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md)'s D5.

## Context

Native files need types, a blob store with its own tables and migrations, a check-out record, an app port and, in later phases, a worker program, a router and a dependency on an external application in alpha. [artifactr ADR-0034](../../artifactr/adr/0034-ports-and-adapters-for-integrations.md) puts each adapter in an extra of the package whose port it implements, but none of this implements an artifactr port: it is a domain built on artifactr.

## Decision

- **A package of its own, `packages/artifactr-files`,** as a deliberate departure from artifactr ADR-0034. artifactr's dependencies and migration chain stay as they are for every application that doesn't edit native files. relayr is the precedent for a package that builds on artifactr from outside.
- **Its PyPI name is `artifactr-files-ai`,** with the suffix artifactr's own distribution has, and it is imported as `artifactr_files`. Nothing in its name uses an app's brand.
- **It depends inward only.** It imports the names in `__all__` of `artifactr`, `artifactr.core` and `artifactr.workspace`, and its SQL layer `lattice_core.sql`; artifactr imports nothing of it. `tests/test_layering.py` holds both.
- **It lives in the monorepo,** so CI runs its tests on every change to artifactr (lattice ADR-0002). Its `artifactr-ai` floor is raised by hand.
- **Its first release is staged.** It joins release-please at `0.0.0` in the manifest, so its first release is 0.1.0 (lattice ADR-0006), and the third publishing stage, after artifactr. Its release pull request stays unqueued until its `artifactr-ai` floor names the artifactr release with the lease. Nothing publishes it to PyPI: a release run never does, and a dispatch needs `PYPI_PUBLISH` and a trusted publisher on PyPI for `artifactr-files-ai`, which no one has added; its `pypi-artifactr-files-ai` environment is created, with its reviewers and tag restriction, before its first dispatch (lattice ADR-0023's amendment, "a package added unreleased").

## Options considered

### Option A: A separate distribution (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Medium: a package's configuration, docs and release |
| artifactr | Unchanged for applications without native files |
| Coupling | artifactr's public API only, held by a test |

**Pros:** its tables, migrations and an alpha dependency stay out of artifactr.
**Cons:** a second package to release, whose floor on artifactr is raised by hand.

### Option B: An extra of artifactr

**Cons:** its tables and migrations would join artifactr's chain for every application, and its worker and router would be in artifactr's wheel.

### Option C: A name built on an app's brand

**Cons:** WordCraft's brand licence forbids it, and the package isn't about one app.

## Trade-off analysis

The package is a domain, not an adapter, and keeping it out of artifactr costs a release and a floor. Option B makes every application carry what few use.

## Consequences

- Easier: artifactr is unchanged for applications that don't edit native files; its only change for them is the lease (artifactr ADR-0071).
- Harder: the package's `artifactr-ai` floor must rise to the release with `Workspace.lease_artifact` before the package's first release.
- Harder: until its environment and pending publisher exist, its release is attached to GitHub and published nowhere.

## Action items

1. [x] The package, its `pyproject.toml`, a `moon.yml` that depends on artifactr and lattice-core, its entries in `release-please-config.json` and the manifest, and its publishing stage.
2. [ ] Raise the `artifactr-ai` floor to the release with the lease, once it is on `main`.
3. [ ] The maintainer, before the first dispatch: the `pypi-artifactr-files-ai` environment and the pending trusted publisher on PyPI.
