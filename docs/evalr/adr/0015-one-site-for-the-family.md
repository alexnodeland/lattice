# ADR-0015: One site for the family

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

Amends [ADR-0010](0010-documentation-site.md), where the site is built and published, and [ADR-0013](0013-docstrings-in-markdown-and-one-docs-build.md), what builds it.

## Context

ADR-0010 built evalr's site from its own `docs/` and `mkdocs.yml`, as artifactr's was built, and published it from `main` at `evalr.alexnodeland.com`. ADR-0013 made its docstrings Markdown, deleted its Griffe extension, and made `make docs` the one build, which `docs.yml` ran. artifactr, reflexr and stackr did the same, each in its own repository. In lattice, [stackr RFC-0003](../../stackr/rfcs/0003-one-repository-lattice.md#docs) makes one site for the family, with a section per package.

## Decision

- **evalr's pages are `docs/evalr/` in lattice,** moved with their history, and its section of [lattice.alexnodeland.com](https://lattice.alexnodeland.com/evalr/), in the order `docs/evalr/.nav.yml` gives. The tools, the strict build, the API reference, the list check, the reference-style root files and the examples checked by running them stand as ADR-0010 and ADR-0013 decided them, configured once, in lattice's `mkdocs.yml`.
- **`moon run lattice:docs` is the build,** in place of `make docs`: the strict build and the list check, over the whole site. CI runs it on every pull request that changes what the site is built from, evalr's code included, and `docs.yml` deploys it from `main`, one run at a time.
- **The changelog page includes `packages/evalr/CHANGELOG.md`** as release-please writes it ([ADR-0014](0014-evalr-in-lattice.md)). Nothing regenerates it at build time, so the site has no "Unreleased" section; the open release pull request shows what is pending.
- **Docstrings stay Markdown.** The site's one mkdocstrings configuration runs lattice's Griffe extension for artifactr's and reflexr's Sphinx roles over every package, evalr's included; evalr's docstrings have none, so it changes nothing there. One build resolves the references between packages, so the libraries no longer load evalr's inventory.
- **The project pages are the family's,** and evalr keeps its changelog and brand pages. Its section's home opens with its lockup; the site's styling is lattice's, so evalr's `brand.css` is gone.
- **`evalr.alexnodeland.com` keeps serving the old pages** until it is retired separately (RFC-0003, D1).

## Consequences

- Easier: one site, one build and one configuration for the family, and a link to a sibling's page is a relative link the strict build checks.
- Harder: evalr's pages live outside its package's directory, which RFC-0003 accepts as the price of one plain build.
- Harder: a Sphinx role written into an evalr docstring would now be rewritten by the extension, into a cross-reference or inline code, where ADR-0013 meant docstrings to be Markdown alone. Review, not the build, keeps them out.
