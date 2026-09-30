# ADR-0013: Docstrings in Markdown, and one docs build

**Status:** Accepted, amended by [ADR-0015](0015-one-site-for-the-family.md)
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Amends [ADR-0010](0010-documentation-site.md): its Griffe extension, and where the site is built.

## Context

ADR-0010 kept a few docstrings' reStructuredText `::` literal blocks as they were, and added a Griffe extension (`scripts/griffe_sphinx_roles.py`) to rewrite them, and any Sphinx role, as the site loads the docstrings. evalr's docstrings have no Sphinx roles, and every other code example in them is a fenced Markdown block, so the extension served six blocks, and the docstrings mixed two markups.

The site was also built in two places with the same steps written twice: CI's Docs job on every pull request, and `docs.yml` on `main`. `make docs` left out the changelog, so it built a different site from either.

## Decision

- **Docstrings are Markdown.** Their code blocks are fenced, as the rest are, and the extension is deleted.
- **`make docs` is the build**: it regenerates the changelog (`make changelog`), builds the site in strict mode, and checks its lists.
- **`docs.yml` runs `make docs`** on every pull request, on every push to `main` and by hand, in a job still named Docs, and deploys only from `main`. Runs on `main` wait their turn, so an older commit never deploys after a newer one; a newer run on a pull request cancels the older one. CI's Docs job is removed.

## Options considered

### Option A: Markdown docstrings, one build (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: no extension, and one definition of the build |
| What a pull request checks | The build that deploys |

**Pros:** one markup; the site built locally, on a pull request and on `main` is built the same way.
**Cons:** `make docs` rewrites `CHANGELOG.md` in the working tree.

### Option B: Keep the extension and both jobs

| Dimension | Assessment |
|---|---|
| Complexity | An extension for six blocks, and a build written three times |
| What a pull request checks | A copy of the build that deploys |

**Pros:** no docstring changes.
**Cons:** the copies can drift, and a docstring can use either markup.

## Trade-off analysis

ADR-0010 preferred rewriting the blocks at build time to editing four docstrings for one renderer. Six fenced blocks read as well in an editor and in `help()` as the rest of evalr's examples do, so the extension no longer buys anything. One workflow that builds on pull requests and deploys from `main` checks exactly what will be published.

## Consequences

- Easier: one markup in docstrings, and one build to change.
- Harder: `make docs` leaves a regenerated `CHANGELOG.md` behind; it is committed only before a release, by `make changelog`.

## Action items

1. [x] Fence the literal blocks, delete the extension, and build the site once, with `make docs`.
