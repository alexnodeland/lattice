# ADR-0017: One site for the family

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

Amends [ADR-0012](0012-documentation-site.md), where the site is built and published and where its changelog comes from, and [ADR-0014](0014-one-docs-build.md), what builds it and what checks the reference pages.

## Context

ADR-0012 built stackr's site from its own `docs/` and `mkdocs.yml`, with reference pages generated from the files they describe, a changelog git-cliff regenerated before every build, and publishing from `main` at `stackr.alexnodeland.com`. ADR-0014 made `make docs` the one build, which `docs.yml` ran, and gave it the reference check. The libraries did the same, each in its own repository. In lattice, [RFC-0003](../rfcs/0003-one-repository-lattice.md#docs) makes one site for the family, with a section per package.

## Decision

- **stackr's pages are `docs/stackr/` in lattice,** moved with their history, and its section of [lattice.alexnodeland.com](https://lattice.alexnodeland.com/stackr/), in the order `docs/stackr/.nav.yml` gives. The tools, the strict build, the list check, the reference-style root files and the generated reference pages stand as ADR-0012 and ADR-0014 decided them, configured once, in lattice's `mkdocs.yml`. The reference pages include the files they describe by their paths from lattice's root.
- **`moon run lattice:docs` is the build,** in place of `make docs`: the strict build and the list check, over the whole site. CI runs it on every pull request that changes what the site is built from, and `docs.yml` deploys it from `main`, one run at a time.
- **stackr's `reference` task checks the reference pages** (ADR-0014's "the Docs build owns the reference check"). It runs `scripts/docs-reference --check` as part of stackr's `check`, whenever stackr's files or its reference pages change, and `make docs-reference` still rewrites the pages.
- **The changelog page includes `packages/stackr/CHANGELOG.md`** as release-please writes it ([ADR-0016](0016-stackr-in-lattice.md)). Nothing regenerates it, so the build needs no full history, and `make changelog` is gone.
- **The project pages are the family's,** and stackr keeps its changelog and brand pages. Its section's home opens with its lockup. stackr's key stylesheet became lattice's, which styles the whole site.
- **`stackr.alexnodeland.com` keeps serving the old pages** until it is retired separately (RFC-0003, D1).

## Consequences

- Easier: one site, one build and one configuration for the family, and a link to a library's page is a relative link the strict build checks.
- Harder: stackr's pages live outside its package's directory, which RFC-0003 accepts as the price of one plain build.
- Harder: a stale reference page fails stackr's `check`, not the site's build, so `moon run lattice:docs` alone doesn't catch one; `moon run stackr:check` does.
