# AGENTS.md

The root [AGENTS.md](../AGENTS.md) applies; this adds what is specific to the documentation site.

## Structure

- The site is built by Zensical from [mkdocs.yml](../mkdocs.yml) at the root, with `docs_dir: docs`.
- Navigation is awesome-nav: each folder's `.nav.yml` orders its section. [docs/.nav.yml](.nav.yml) lists lattice's own pages, ADRs and RFCs; `docs/<package>/.nav.yml` orders each package's.
- **A new page must be added to its folder's `.nav.yml`**, or it is missing from the menu.
- `docs/<package>/` holds a package's pages: `index.md`, `getting-started.md`, `architecture.md`, `guides/`, `reference/`, `adr/`, `rfcs/`, and `spec/` where it has a formal spec (ADR-0025).
- `AGENTS.md` files are excluded from the site (`exclude_docs` in `mkdocs.yml`).

## Decisions and proposals

- ADRs and RFCs are numbered per scope: `docs/adr/` and `docs/rfcs/` are lattice's, `docs/<package>/adr/` and `docs/<package>/rfcs/` each package's. Take the next free four-digit number in that folder: `NNNN-a-short-title.md`.
- Start from [adr/template.md](adr/template.md) or [rfcs/template.md](rfcs/template.md), add the file to the folder's index (`README.md` or `index.md`) and to the `.nav.yml` that lists it.
- **Accepted ADRs keep their body.** A changed decision gets a new ADR that supersedes the old one, and only the old one's Status line changes; a small amendment is appended as a dated `## Amendment (YYYY-MM-DD)` section.

## Writing pages

- A blank line before every list; nested items indented by the parent's text (two spaces after `-`, three after `1.`). `scripts/check_site.py` fails on a list that rendered as text.
- API reference pages use mkdocstrings directives (`::: artifactr.files.manifest`); don't copy docstrings into pages.
- Include repository files with `pymdownx.snippets` (paths from the root) instead of copying them.
- Relative links must resolve: the build is strict, and nightly runs lychee over every `*.md`. A site that refuses lychee goes in [.lycheeignore](../.lycheeignore), with a comment saying why.

## Commands

```bash
moon run lattice:docs         # strict build, then scripts/check_site.py over site/
moon run lattice:docs-serve   # live reload at http://localhost:8000
```
