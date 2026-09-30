# ADR-0014: One site for the family

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

Amends [ADR-0011](0011-documentation-site-and-brand.md): where the site is built and published, and how its references resolve.

## Context

ADR-0011 set relayr up to build its own site, as its siblings built theirs: from its own `mkdocs.yml` with `make docs`, published from `main` at `relayr.alexnodeland.com`, with cross-references resolved through artifactr's and reflexr's inventories. That site was never published: relayr's foundation was never merged, and its domain had no DNS record. In lattice, [stackr RFC-0003](../../stackr/rfcs/0003-one-repository-lattice.md#docs) makes one site for the family, with a section per package.

## Decision

- **relayr's pages are `docs/relayr/` in lattice,** and its section of [lattice.alexnodeland.com](https://lattice.alexnodeland.com/relayr/adr/), in the order `docs/relayr/.nav.yml` gives. The section starts at its decisions until relayr writes a landing page. The tools, the strict build and the list check stand as ADR-0011 decided them, configured once, in lattice's `mkdocs.yml`.
- **`moon run lattice:docs` is the build,** in place of `make docs`: the strict build and the list check, over the whole site. CI runs it on every pull request that changes what the site is built from, and `docs.yml` deploys it from `main`, one run at a time.
- **The changelog page includes `packages/relayr/CHANGELOG.md`** as release-please writes it ([ADR-0013](0013-relayr-in-lattice.md)), and nothing regenerates it at build time.
- **Docstrings stay Markdown, and one build resolves their references.** A cross-reference to artifactr or reflexr resolves within the site, with no inventory. The site's one mkdocstrings configuration runs lattice's Griffe extension for artifactr's and reflexr's Sphinx roles over every package; relayr's docstrings have none, so it changes nothing there.
- **The brand stands,** and relayr's section keeps its brand page. The site's styling is lattice's, so relayr's `brand.css` is gone.

## Consequences

- Easier: relayr's pages are published, in the same site as the libraries it bridges, and its links to their pages are relative links the strict build checks.
- Harder: relayr's pages live outside its package's directory, which RFC-0003 accepts as the price of one plain build.
