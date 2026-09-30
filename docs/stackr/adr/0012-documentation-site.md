# ADR-0012: The documentation site, and publishing it from main

**Status:** Accepted; amended by [ADR-0014](0014-one-docs-build.md), [ADR-0016](0016-stackr-in-lattice.md) and [ADR-0017](0017-one-site-for-the-family.md)
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

## Context

RFC-0001 phase 6 asks for a documentation site in the family's style, built in strict mode in CI. stackr's design is already Markdown under `docs/`: the architecture, the ADRs and the RFCs. It is evergreen and read on GitHub as well as on a site, so the site has to use it as it is, not copies. The site is to be published at `https://stackr.alexnodeland.com`.

The libraries built their sites first. artifactr chose the tools ([its ADR-0023](https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0023-documentation-site.md)) and then publishing from `main` ([its ADR-0026](https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0026-publishing-the-documentation-site.md)); reflexr turned artifactr's brand into a system the four projects share ([its ADR-0032](https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0032-documentation-site.md) and [ADR-0033](https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0033-publishing-the-documentation-site.md)); and evalr followed both ([its ADR-0010](https://github.com/alexnodeland/evalr/blob/main/docs/adr/0010-documentation-site.md)). Two amendments came after them, in all three: lists must render as they do on GitHub, and the site's changelog must be `main`'s. A reader moving between the four sites should find the same structure, tools and conventions.

stackr differs from the libraries in three ways that matter here:

- **It has no Python package,** so there is no API reference to generate from docstrings. Its reference is its configuration: `compose.yaml`, `.env.example`, the Collector's, Grafana's and the gateway's files, `copier.yml` and `template/`, the Makefile and `versions.env`.
- **That configuration changes often, and some of it without a person.** A reference written by hand would be wrong the first time a port, a model or a question changed, and Dependabot changes the images' tags in `compose.yaml` every week.
- **Its brand is the family's key.** In the family's system, each library prints in two of the three process inks and stackr in key, the quiet plate the others sit on: its mark is three slabs stacked along the family's diagonal. The files were drawn by the family's generator, at the family's layout.

## Decision

### The site

- **Built as the libraries' are.** Zensical builds it from `mkdocs.yml`, with `docs_dir: docs` and the modern theme variant; `pymdownx.snippets` includes the repository's root files (`CONTRIBUTING.md`, `CHANGELOG.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `LICENSE`) from small pages under `docs/project/`, whose reference-style link definitions replace the files' own; and the navigation is the family's: home, getting started, guides, reference, design (the architecture, every ADR and RFC, and their templates) and project, with the brand page. With no package, there is no mkdocstrings plugin. The tools are a dependency group, `docs`, included in `dev`.
- **Guides written from the files.** Each guide covers one concern (the stack and its profiles, local Supabase, the gateway, observability, Langfuse, the application template, the smoke tests, validation and CI, security, troubleshooting), and every command, port and setting in them was checked against the Makefile, `compose.yaml`, `.env.example` and `versions.env` when written. Where the existing documents and the files disagreed, the guides describe the files. Pages under `docs/` link to files outside it by their GitHub URL.

### The reference, generated

- **Each reference page is written by hand around blocks that `scripts/docs-reference` generates** from the file the page describes, between `<!-- generated: NAME -->` and `<!-- end generated -->`: the Compose services, profiles, networks and volumes; the settings in `.env.example`; the Collector's pipelines and components; Grafana's data sources, links and dashboards; the gateway's models, fallbacks, guardrails and settings; the template's questions, derived values and generated files; the Makefile's targets and variables; and the pins in `versions.env` and `copier.yml`. Each page also includes its file in full, by snippet.
- **A page can't drift from its file.** `scripts/docs-reference --check` fails when a block is out of date, a page names a block the script doesn't know, or a block is on no page. `make validate`, `make docs` and CI's Docs job run it, and `make docs-reference` rewrites the blocks. The script also fails on a Compose service it has no one-line role for, and on a published port whose default in `compose.yaml` differs from `.env.example`'s.
- **Images are named without their tags.** `compose.yaml` pins them, and Dependabot's weekly updates to them then pass the check without a regenerated page. Pins that change by hand (`versions.env`, the template's library revisions) are shown, and bumping one includes `make docs-reference`.

### The brand

- **stackr's brand is the family's, in key**, stated in [`docs/assets/brand/README.md`](../assets/brand/README.md): the files in `docs/assets/brand/`, and one stylesheet, `docs/assets/stylesheets/brand.css`, with the palette, logo, favicon and typefaces applied through theme settings. Key has no hue to tell links from text, so links are underlined. The README carries the banner.
- **The banner's mark is placed three grid units left of the family's origin**: at (824, 0.8) rather than (845.6, 0.8). At the family's placement, the top slab's right end ran 7 units past the panel's edge and its cut was clipped, where the other marks run off the panel only where they are meant to. Only the placement changed: the mark, its scale and the text are the family's.

### Building and publishing

- **The build is strict everywhere.** `make docs` and CI's Docs job check the reference pages, then run `zensical build --strict --clean`, so a broken link or anchor fails the build.
- **Lists render as they do on GitHub.** The `mdx_truly_sane_lists` extension, with `nested_indent: 2`, makes two spaces nest a list, as GitHub does; a nested item is indented by its parent's text, two spaces after `-` and three after `1.`. A blank line goes before every list. `scripts/check_site.py`, the family's, checks the built site in `make docs` and CI: a paragraph or list item containing a line that starts with a list marker is a list that rendered as text, and fails the build.
- **The site's changelog is `main`'s.** `CHANGELOG.md` is generated by git-cliff from the commit history and never edited by hand. The Docs job and the publishing workflow check out the whole history (`fetch-depth: 0`) and regenerate it before building, so the site's changelog page is always current, and `make changelog` regenerates the file itself before a release. The whitespace hooks leave git-cliff's output as it is.
- **Every push to `main` publishes the site.** `.github/workflows/docs.yml` builds it as CI does and deploys it to GitHub Pages, on pushes to `main` and by hand, one deployment at a time. The custom domain is set in the repository's Pages settings, with GitHub Actions as the source; deployments from a workflow ignore a `CNAME` file, so the repository has none. `site_url` is the custom domain, so canonical links and the sitemap point there. The site shows `main`, not a release.

## Options considered

### Tools

| Option | Matches the family | Strict build | Direction |
|---|---|---|---|
| **Zensical, as the libraries (chosen)** | Yes | Yes | The successor its authors are developing; pre-1.0 |
| MkDocs 1.6 with Material for MkDocs | Nearly: the same configuration | Yes | Maintenance only |
| Sphinx with MyST | No | Yes (`-W`) | Active |

### The reference

| Option | Stays true to the files | Readable as a reference | Cost |
|---|---|---|---|
| **Generated blocks, committed, with a check (chosen)** | Yes: a stale page fails CI | Tables of what people look up, beside the prose | A script to maintain, and a regeneration step when a file changes |
| Written by hand | Only until the next change | Yes | Every change to a file needs a matching edit that nothing checks |
| Generated at build time, not committed | Yes | Yes, on the site only | The pages don't exist in the repository, and `make docs-serve` needs a step first |
| The files included verbatim, and nothing else | Yes | No: a reader searches YAML for a port | None |

### Publishing

| Option | Site matches `main` | Effort per change |
|---|---|---|
| **Deploy on every push to `main` (chosen)** | Always | None |
| Deploy by hand | Only after someone runs it | A manual step each time |
| Deploy on releases only | At each release | None, but there is no release yet, so no site |

## Trade-off analysis

The libraries weighed the tools on their merits, and nothing about stackr changes that weighing; the family is read as a whole, and a second toolchain would mean two ways to configure, brand and check the same kind of site. The risks they accepted (a pre-1.0 tool; links inside included snippets are not checked) are accepted here for the same reasons, with the same mitigations: the version is pinned in `uv.lock`, the fallback to Material for MkDocs is one line of configuration, and the root files keep reference-style links that each including page redefines.

The reference is where stackr differs, and where a site could most easily mislead: a port or a model name on a page that no longer matches the file is worse than no page. Generating the facts and checking them in CI costs one script, and makes the reference as trustworthy as the libraries' API references, which are generated from docstrings. Committing the generated blocks keeps the pages readable in the repository, and shows a change to them in the same pull request as the change to the file. Leaving the images' tags out keeps Dependabot's pull requests free of documentation churn, at the cost of a reader looking up an exact version in `compose.yaml`.

Publishing from every push follows from evergreen documentation: a guide changes in the same pull request as the configuration it describes, and a site deployed by hand would fall behind without anyone noticing.

## Consequences

- Easier: the guides, the reference and the design records are one site, built from the repository, and the reference cannot drift from the configuration.
- Easier: a broken link or anchor, a list that renders as text, or a reference page that no longer matches its file fails CI, and a merged change is live within minutes.
- Harder: changing a file a reference page describes needs `make docs-reference` in the same pull request; `make validate` says so.
- Harder: root files must keep their links reference-style, and a new link in one of them needs a definition in its `docs/project/` page. Strict mode does not catch a missing one, so check the included pages when changing those files.
- Harder: the guides' prose is checked when it is written, not in CI. A change to a command, port or behaviour they describe updates them in the same pull request.
- Harder: Zensical is young. Upgrades should be checked with a strict build like any other dependency update.
- Revisit: versioned documentation, once there are several releases; generated reference pages for Tempo's, Loki's, Prometheus's and Pyroscope's configurations, which the guides describe by hand for now.

## Action items

1. [x] Build the site, the reference generator, the brand and the branded README (RFC-0001 phase 6).
2. [x] Build the site in strict mode in CI, with the reference check.
3. [x] Deploy the site on pushes to `main`, and point the README at it.
4. [ ] Consider versioned documentation once there are several releases.
