# ADR-0023: The documentation site

**Status:** Accepted, amended by [0026](0026-publishing-the-documentation-site.md) and [0050](0050-one-docs-build.md)
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

RFC-0001 phase 7 asks for a documentation website with guides and an API reference, built in CI with no warnings. The project's documentation already exists as Markdown under `docs/`: the architecture, the thread protocol, the ADRs and the RFCs. They are evergreen and read on GitHub as well as on a site, so the site has to use them as they are rather than copies.

The site needs:

- an API reference generated from the library's docstrings, which follow the Google style but cross-reference with Sphinx roles (`:class:`, `:meth:`, `:func:`)
- Mermaid diagrams, which the architecture uses
- search, code copy buttons, light and dark schemes, and the project's brand
- the repository's root files (`CONTRIBUTING.md`, `CHANGELOG.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `LICENSE`) without duplicating them
- a strict build that fails on broken links and anchors, so the site cannot rot silently

The obvious toolchain is Material for MkDocs with mkdocstrings. Its authors now build Zensical as its successor: a new static site generator that reads `mkdocs.yml`, while Material for MkDocs continues in maintenance, and MkDocs itself has not been released since 1.6.1 in August 2024. Zensical is pre-1.0 (0.0.66), so the question was whether its mkdocstrings support is good enough to start there.

A spike answered it. With Zensical 0.0.66 and mkdocstrings-python 2.0.9:

- `:::` directives render, with signatures, cross-references between pages (autorefs), and links into the Python, Pydantic and pydantic-ai inventories
- Mermaid fences render, with the theme's colours
- `--strict` fails the build on a missing page or anchor in a page's own source
- a clean build of the whole site takes about two seconds

It also found two limits:

- Links inside content included with `pymdownx.snippets` are not checked, even in strict mode.
- mkdocstrings renders Sphinx roles literally, and 73 of them are spread over 22 modules.

## Decision

- **Zensical builds the site**, from `mkdocs.yml` with `docs_dir: docs`, using its modern theme variant. The brand's palette, logo, favicon and typefaces are applied with theme settings and one stylesheet (`docs/assets/stylesheets/brand.css`). The configuration avoids Python YAML tags (Zensical resolves the Mermaid fence's format function from a plain string), so `mkdocs.yml` stays valid YAML for the `check-yaml` hook.
- **mkdocstrings-python renders the API reference**, one page per package, grouped by concept, covering exactly each package's `__all__`. `griffe-pydantic` lists the fields of Pydantic models.
- **A small Griffe extension converts Sphinx roles** into cross-references when the docstrings are loaded (`scripts/griffe_sphinx_roles.py`). Each role is resolved in the scope of the object whose docstring contains it; a role that cannot be resolved, or that names an internal module, becomes inline code. The library's docstrings are unchanged.
- **Root files are included, not copied.** Small pages under `docs/project/` include them with `pymdownx.snippets`. Their links are reference-style, with the definitions at the end of each file, and each including page redefines them for the site (the last definition wins). Pages under `docs/` that point outside it use GitHub URLs, because the site cannot serve those files.
- **The build is strict everywhere.** `make docs` and CI's Docs job run `zensical build --strict --clean`, so a broken link or anchor fails the build, and the cache cannot hide a warning.
- **Publishing is separate and manual.** `.github/workflows/docs.yml` builds and deploys to GitHub Pages only when run by hand (`workflow_dispatch`). Whether and when to publish is the maintainer's decision.
- **The tools are a dependency group**, `docs`, included in `dev`, with minimum versions like the other groups and exact versions in `uv.lock`.

## Options considered

### Option A: Zensical with mkdocstrings (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one config file, Markdown next to the code |
| Maturity | Pre-1.0 and releasing often; configuration may change |
| API reference | mkdocstrings-python, verified to render in Zensical |
| Strict build | Yes, for links and anchors in page source |
| Direction | The successor its authors are developing |

**Pros:** fast builds; reads the same `mkdocs.yml` as the tools it replaces; the ecosystem (mkdocstrings, pymdown-extensions) carries over; its link validation checks anchors as well as pages.
**Cons:** a young tool; links in included snippets are not validated.

### Option B: MkDocs 1.6 with Material for MkDocs 9.7 and mkdocstrings

| Dimension | Assessment |
|---|---|
| Complexity | Low: the same configuration, give or take a YAML tag |
| Maturity | Mature and widely used |
| API reference | mkdocstrings-python, its native home |
| Strict build | Yes |
| Direction | Maintenance only: MkDocs is unreleased since 2024, and Material's authors moved to Zensical |

**Pros:** the most proven option today; hooks allow build-time scripts.
**Cons:** starts a new site on a stack its maintainers are moving away from.

### Option C: Sphinx with MyST and autodoc

| Dimension | Assessment |
|---|---|
| Complexity | Medium: reStructuredText idioms under MyST, a theme, and extensions for Mermaid and Markdown |
| Maturity | Mature |
| API reference | autodoc understands Sphinx roles natively |
| Strict build | Yes (`-W`) |
| Direction | Active |

**Pros:** the docstrings' roles work without a conversion step, and cross-references are checked by the tool that defined them.
**Cons:** the existing docs are GitHub-flavoured Markdown with tables and Mermaid fences, which need MyST configuration and extensions to render the same; a heavier toolchain for contributors used to Markdown.

## Trade-off analysis

The deciding question was whether a pre-1.0 tool was ready. The spike showed that everything this site needs works in Zensical today, and the remaining risk is contained: `mkdocs.yml` is the same file Material for MkDocs reads, so falling back to Option B means changing the tool in `pyproject.toml` and one line of configuration (the Mermaid fence's format, which MkDocs needs as a `!!python/name:` tag). Starting on Material would buy maturity now at the cost of migrating later.

Sphinx would have made the Sphinx roles free, but the roles are a small, mechanical problem solved by a 70-line extension, while the documentation's Markdown is the larger body of work, and it already renders as intended in the MkDocs family.

The two limits found in the spike have narrow fixes. The Griffe extension keeps the library's docstrings untouched, rather than rewriting 73 cross-references for one renderer. For included root files, reference-style links keep a single copy of each file that renders correctly in both places.

## Consequences

- Easier: every guide, the reference and the design records are one site built from the repository, and the reference cannot drift from the code.
- Easier: a broken link or anchor in a page fails CI.
- Harder: root files must keep their links reference-style, and a new link in one of them needs a definition in its `docs/project/` page. Strict mode does not catch a missing one, so check the included pages when changing those files.
- Harder: Zensical is young. Its version is pinned in `uv.lock`, and upgrades should be checked with a strict build like any other dependency update.
- Revisit when Zensical reaches 1.0, or if its native configuration format replaces `mkdocs.yml` as the recommended one.

## Amendment (2026-09-29): lists render as they do on GitHub

Python-Markdown, which the site uses, needs four spaces to nest a list and a blank line before a list that follows a paragraph; GitHub needs neither. The repository's Markdown nests by two spaces, so most nested lists on the site were flat, and a few lists rendered as a paragraph of "- " text.

- **The `mdx_truly_sane_lists` extension** makes two spaces nest, as on GitHub. A nested item is indented by its parent's text: two spaces after `-`, three after `1.`.
- **A blank line goes before every list.** The pages that lacked one are fixed.
- **`scripts/check_site.py` checks the built site** in `make docs` and in CI: a paragraph or list item containing a line that starts with a list marker is a list that rendered as text, and fails the build. reflexr made the same change in its ADR-0032.

## Action items

1. [x] Build the site, the brand and the branded README (RFC-0001 phase 7).
2. [x] Build the site in strict mode in CI.
3. [x] Decide whether to publish the site, then enable GitHub Pages and run the Docs workflow ([ADR-0026](0026-publishing-the-documentation-site.md)).
