# ADR-0053: One site for the family

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

Amends [ADR-0023](0023-documentation-site.md), where the site is built; [ADR-0026](0026-publishing-the-documentation-site.md), where it is published; and [ADR-0050](0050-one-docs-build.md), what builds it.

## Context

ADR-0023 built artifactr's site from its own `docs/` and `mkdocs.yml`, ADR-0026 published it from `main` at `artifactr.alexnodeland.com`, and ADR-0050 made `make docs` the one build, which `docs.yml` ran. reflexr, evalr and stackr did the same, each in its own repository. In lattice, [stackr RFC-0003](../../stackr/rfcs/0003-one-repository-lattice.md#docs) makes one site for the family, with a section per package.

## Decision

- **artifactr's pages are `docs/artifactr/` in lattice,** moved with their history, and its section of [lattice.alexnodeland.com](https://lattice.alexnodeland.com/artifactr/), in the order `docs/artifactr/.nav.yml` gives. The tools, the strict build, the API reference, the list check and the reference-style root files stand as ADR-0023 and ADR-0050 decided them, configured once, in lattice's `mkdocs.yml`.
- **`moon run lattice:docs` is the build,** in place of `make docs`: the strict build and the list check, over the whole site. CI runs it on every pull request that changes what the site is built from, artifactr's code included, and `docs.yml` deploys it from `main`, one run at a time.
- **The changelog page includes `packages/artifactr/CHANGELOG.md`** as release-please writes it ([ADR-0052](0052-artifactr-in-lattice.md)). Nothing regenerates it at build time, so the site has no "Unreleased" section; the open release pull request shows what is pending.
- **One build resolves the references between packages,** so no inventory of a sibling's is loaded, and the Griffe extension for Sphinx roles is one script, at lattice's root, for artifactr's docstrings and reflexr's.
- **The project pages are the family's.** lattice's contributing guide and security policy hold artifactr's commands and its tenant-isolation scope ([ADR-0011](0011-workspace-scoped-artifacts-and-tenant-handles.md)). artifactr keeps its changelog and brand pages, and its section's home opens with its lockup; the site's styling is lattice's, so artifactr's `brand.css` is gone.
- **`artifactr.alexnodeland.com` keeps serving the old pages** until it is retired separately (RFC-0003, D1).

## Consequences

- Easier: one site, one build and one configuration for the family, and a link to a sibling's page is a relative link the strict build checks.
- Harder: artifactr's pages live outside its package's directory, which RFC-0003 accepts as the price of one plain build.
- Harder: the site's one mkdocstrings configuration serves every package, so a change made for artifactr's docstrings is made for all of them.
