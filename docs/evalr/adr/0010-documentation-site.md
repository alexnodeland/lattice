# ADR-0010: The documentation site, and publishing it from main

**Status:** Accepted, amended by [ADR-0013](0013-docstrings-in-markdown-and-one-docs-build.md) and [ADR-0015](0015-one-site-for-the-family.md)
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

## Context

RFC-0001 phase 6 asks for a documentation site in the family's style, built in strict mode in CI. The project's documentation already exists as Markdown under `docs/`: the architecture, the ADRs and the RFCs. It is evergreen and read on GitHub as well as on a site, so the site has to use it as it is, not copies. The site is to be published at `https://evalr.alexnodeland.com`, and the repository's GitHub Pages settings already serve that domain from a workflow.

artifactr built its site first, and recorded the choice of tools in [its ADR-0023](https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0023-documentation-site.md) and the choice to publish from `main` in [its ADR-0026](https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0026-publishing-the-documentation-site.md). The four projects of the family (artifactr, reflexr, evalr, stackr) share a brand: one grid, one stroke, one typeface, and a hue for each. A reader moving between their sites should find the same structure, the same navigation and the same conventions.

The site needs:

- an API reference generated from the docstrings, which follow the Google style, for every public package
- Mermaid diagrams, which the architecture uses
- search, code copy buttons, light and dark schemes, and evalr's brand
- the repository's root files (`CONTRIBUTING.md`, `CHANGELOG.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `LICENSE`) without duplicating them
- a strict build that fails on broken links and anchors

Two things differ from artifactr. evalr's docstrings use no Sphinx cross-reference roles, but four of them introduce a code block with reStructuredText's `::` marker, which Markdown would show literally. And evalr's guides show evaluators backed by services (a language model, TypeSafe's API, Langfuse, the Hugging Face Hub), so their examples cannot run in CI as they are written.

## Decision

- **The site is built as artifactr's is**, with the same tools, configuration and structure: Zensical from `mkdocs.yml` with `docs_dir: docs` and its modern theme variant; mkdocstrings-python for the API reference, one page per package, grouped by concept, covering exactly each package's `__all__`, with `griffe-pydantic` listing the fields of Pydantic models; `pymdownx.snippets` including the root files from pages under `docs/project/`; and the same navigation: home, getting started, concepts, guides, reference, design (the architecture, every ADR and RFC) and project.
- **The brand is the family's**, in evalr's green: the brand files in `docs/assets/brand/` and one stylesheet, `docs/assets/stylesheets/brand.css`, with the palette, logo, favicon and typefaces applied through theme settings. The README carries the banner.
- **A small Griffe extension rewrites reStructuredText idioms** when the docstrings are loaded (`scripts/griffe_sphinx_roles.py`, artifactr's extension extended): a paragraph's closing `::` becomes a colon, so the indented block after it renders as code, and any Sphinx role becomes a cross-reference, or inline code where it cannot be resolved. The library's docstrings are unchanged.
- **The build is strict everywhere.** `make docs` and CI's Docs job run `zensical build --strict --clean`, so a broken link or anchor fails the build.
- **Every example is checked by running it** before it is published, offline: evalr's in-memory adapters, DSPy's `DummyLM`, a fake of TypeSafe's API on its SDK's transport, and fakes of Langfuse and the Hub stand in for the services. The pages show the code as an application would write it.
- **Every push to `main` publishes the site.** `.github/workflows/docs.yml` builds it as CI does and deploys it to GitHub Pages, on pushes to `main` and by hand. The custom domain is set in the repository's Pages settings, with GitHub Actions as the source; deployments from a workflow ignore a `CNAME` file, so the repository has none. `site_url` is the custom domain, so canonical links and the sitemap point there. The site shows `main`, not a release.
- **The tools are a dependency group**, `docs`, included in `dev`, with minimum versions like the other groups and exact versions in `uv.lock`.

## Options considered

### Tools

| Option | Matches the family | API reference | Strict build | Direction |
|---|---|---|---|---|
| **Zensical with mkdocstrings, as artifactr (chosen)** | Yes | mkdocstrings-python | Yes | The successor its authors are developing; pre-1.0 |
| MkDocs 1.6 with Material for MkDocs | Nearly: the same configuration | mkdocstrings-python | Yes | Maintenance only |
| Sphinx with MyST | No | autodoc | Yes (`-W`) | Active |

### Publishing

| Option | Site matches `main` | Effort per change |
|---|---|---|
| **Deploy on every push to `main` (chosen)** | Always | None |
| Deploy by hand | Only after someone runs it | A manual step each time |
| Deploy on releases only | At each release | None, but guides for unreleased features stay unpublished |

## Trade-off analysis

artifactr's ADR-0023 weighed the tools on their own merits and chose Zensical; nothing about evalr changes that weighing, and one thing adds to it: the family is read as a whole, and a second toolchain would mean two ways to configure, brand and check the same kind of site. The risks artifactr accepted (a pre-1.0 tool; links inside included snippets are not checked) are accepted here for the same reasons, with the same mitigations: the version is pinned in `uv.lock`, the fallback to Material for MkDocs is one line of configuration, and the included root files keep reference-style links that each including page redefines.

The Griffe extension grows by two regular expressions rather than editing four docstrings for one renderer: the docstrings read naturally in an editor and in `help()`, and the site renders them as intended.

Publishing from every push to `main` follows from evergreen documentation: a guide changes in the same pull request as the code it describes, and a site deployed by hand would fall behind without anyone noticing. evalr is not yet released, so the site describes `main` until versioned documentation is worth its cost.

## Consequences

- Easier: every guide, the reference and the design records are one site, built from the repository, and the reference cannot drift from the code.
- Easier: a broken link or anchor fails CI, and a merged documentation change is live within minutes.
- Harder: root files must keep their links reference-style, and a new link in one of them needs a definition in its `docs/project/` page. Strict mode does not catch a missing one, so check the included pages when changing those files.
- Harder: the guides' examples are checked when they are written, not in CI. A change to an API the guides use should rerun their examples.
- Harder: Zensical is young. Upgrades should be checked with a strict build like any other dependency update.
- The site can describe features that are on `main` but not in a release. Revisit with versioned documentation once there are several releases.

## Amendment (2026-09-29): lists render as they do on GitHub

Python-Markdown, which the site uses, needs four spaces to nest a list and a blank line before a list that follows a paragraph; GitHub needs neither. The repository's Markdown nests by two spaces, so most nested lists on the site were flat, and a few lists rendered as a paragraph of "- " text.

- **The `mdx_truly_sane_lists` extension** makes two spaces nest, as on GitHub. A nested item is indented by its parent's text: two spaces after `-`, three after `1.`.
- **A blank line goes before every list.** The pages that lacked one are fixed.
- **`scripts/check_site.py` checks the built site** in `make docs` and in CI: a paragraph or list item containing a line that starts with a list marker is a list that rendered as text, and fails the build. reflexr made the same change in its ADR-0032.

## Action items

1. [x] Build the site, the brand and the branded README (RFC-0001 phase 6).
2. [x] Build the site in strict mode in CI.
3. [x] Deploy the site on pushes to `main`, and point the project's URLs at it.
4. [ ] Consider versioned documentation once there are several releases.
