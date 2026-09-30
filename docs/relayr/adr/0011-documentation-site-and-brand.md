# ADR-0011: The documentation site and brand

**Status:** Accepted, amended by [ADR-0014](0014-one-site-for-the-family.md)
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

relayr's documentation is Markdown under `docs/`: the architecture, the ADRs and the RFCs, read on GitHub and on a site at `https://relayr.alexnodeland.com`, which the repository's GitHub Pages settings serve from a workflow. Its siblings build their sites one way, and changed it twice after they began: evalr moved its docstrings to Markdown and dropped its Griffe extension, and all four moved to one docs build ([evalr ADR-0013][e-adr-0013], [reflexr ADR-0046][r-adr-0046], [artifactr ADR-0050][a-adr-0050]). relayr starts from where they ended.

The family also shares one brand system, stated on [reflexr's brand page][r-brand]: one grid, one stroke, one typeface, and print-proofing logic, in which each coloured library prints with two of the three process inks, overprinting into its working colour, and stackr prints in key alone. The three pairs of inks are taken: artifactr's magenta and cyan, reflexr's yellow and magenta, and evalr's yellow and cyan.

## Decision

- **The site is built as the siblings' are:** Zensical from `mkdocs.yml`; mkdocstrings-python with `griffe-pydantic`, one reference page per package covering its `__all__`; `pymdownx.snippets` including the root files from pages under `docs/project/`; `mdx_truly_sane_lists`, so lists nest by two spaces as on GitHub; and `scripts/check_site.py`, which fails the build on a list that rendered as text. The tools are the `docs` dependency group.
- **Docstrings are Markdown**, as evalr's are: fenced code blocks, and cross-references written as Markdown links (``[`Workspace`][artifactr.workspace.Workspace]``), resolved through artifactr's and reflexr's inventories. There is no Griffe extension for Sphinx roles.
- **One docs build.** `make docs` regenerates the changelog, builds the site in strict mode and checks its lists. `docs.yml` runs it on every pull request, on every push to `main` and by hand, and deploys only from `main`. Its concurrency group is the ref's: runs on `main` wait their turn, so an older commit never deploys after a newer one, and a newer run on a pull request cancels the older one.
- **The site shows `main`.** The custom domain is set in the Pages settings, with GitHub Actions as the source, so the repository has no `CNAME` file.
- **relayr prints on one plate: magenta, the ink artifactr and reflexr share.** Its mark is two strokes on the family's diagonal, each two thirds of the grid's height and half a stroke apart. They overlap in the middle third, where the plate prints twice, and that double hit is relayr's overprint and working colour: a deep magenta, `#9E0A5E` on paper and `#FFDCEC` on screen. The files follow the family's layout to the unit, and [the brand page](../assets/brand/README.md) states the rest.

## Options considered

### Docstrings

| Option | Markup | Tooling |
|---|---|---|
| **Markdown, as evalr's (chosen)** | One, the site's | None beyond mkdocstrings |
| Sphinx roles, as artifactr's and reflexr's | Two: roles in docstrings, Markdown everywhere else | A Griffe extension that rewrites the roles as the site loads them |

artifactr and reflexr keep their extension because their docstrings already use roles. relayr has no docstrings yet, so it starts with the markup the site reads natively.

### The brand's inks

| Option | Its own working colour | Within the system |
|---|---|---|
| **One plate, magenta, overprinting itself (chosen)** | A deep magenta, which no sibling works in | As stackr prints in key alone; the plate is the ink its two libraries share |
| Two inks: artifactr's indigo and reflexr's red | Their overprint is a near-black, beside stackr's key | Inks that are other libraries' overprints, not a printer's |
| A pair of process inks | Only a sibling's | Every pair is taken |
| A fifth, spot ink, such as orange | Yes | Outside the printer's four inks |

## Consequences

- Easier: the site is built, checked and published exactly as the siblings' are, and a docstring reads the same in an editor and on the site.
- Easier: relayr reads as the family's fifth member, and as the one between artifactr and reflexr.
- Harder: magenta is the ink artifactr and reflexr share and the colour that marks interaction on their sites, so relayr's mark is the family's closest to its neighbours in colour, and its working colour is the nearest to reflexr's red. Its shape carries the difference.
- Harder: the family pages in the siblings' repositories (reflexr's brand page and its family sheet) list four marks, and need relayr added there.

[a-adr-0050]: https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0050-one-docs-build.md
[e-adr-0013]: https://github.com/alexnodeland/evalr/blob/main/docs/adr/0013-docstrings-in-markdown-and-one-docs-build.md
[r-adr-0046]: https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0046-one-docs-build.md
[r-brand]: https://github.com/alexnodeland/reflexr/blob/main/docs/assets/brand/README.md#the-family
