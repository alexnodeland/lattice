# ADR-0014: One docs build

**Status:** Accepted; amended by [ADR-0017](0017-one-site-for-the-family.md)
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Amends [ADR-0012](0012-documentation-site.md): where the site is built, and what checks its reference pages.

## Context

ADR-0012 wrote the build's steps three times, in `make docs`, CI's Docs job and `docs.yml`, and ran it in two places: CI's Docs job on every pull request and push, and `docs.yml` on every push to `main`, so each push to `main` built the site twice. `make docs` left out the changelog, so it built a different site from either workflow. And `scripts/docs-reference --check` ran four times: in `make validate`, in `make docs`, and in each workflow.

evalr had the same arrangement, and changed it in [its ADR-0013](https://github.com/alexnodeland/evalr/blob/main/docs/adr/0013-docstrings-in-markdown-and-one-docs-build.md). stackr follows it, so the family's sites are built the same way.

## Decision

- **`make docs` is the build**: it regenerates the changelog (`make changelog`), checks the reference pages against their files, builds the site in strict mode, and checks its lists.
- **`docs.yml` runs `make docs`** on every pull request, on every push to `main` and by hand, in a job named Docs, and deploys only from `main`. Runs on `main` wait their turn, so an older commit never deploys after a newer one; a newer run on a pull request cancels the older one. CI's Docs job is removed.
- **The Docs build owns the reference check.** `make validate` no longer runs `scripts/docs-reference --check`; a stale reference page fails the Docs job instead.

## Options considered

### Option A: One build, in `docs.yml` (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one definition of the build |
| What a pull request checks | The build that deploys |

**Pros:** the site built locally, on a pull request and on `main` is built the same way, and each push to `main` builds it once.
**Cons:** `make docs` rewrites `CHANGELOG.md` in the working tree, and `make validate` alone no longer catches a stale reference page.

### Option B: Keep both jobs

| Dimension | Assessment |
|---|---|
| Complexity | A build written three times, and a check run four times |
| What a pull request checks | A copy of the build that deploys |

**Pros:** no change.
**Cons:** the copies can drift, and every push to `main` builds the site twice.

## Trade-off analysis

One workflow that builds on pull requests and deploys from `main` checks exactly what will be published, and matches evalr's. The reference check belongs with the build that publishes the pages it checks; running it in `make validate` as well only repeated it.

## Consequences

- Easier: one build to change, and the same one in every sibling repository.
- Harder: `make docs` leaves a regenerated `CHANGELOG.md` behind; it is committed only before a release, by `make changelog`.
- Harder: after changing a file a reference page describes, `make docs` (not `make validate`) says the page needs `make docs-reference`.

## Action items

1. [x] Build the site once, with `make docs`, in `docs.yml`, and remove CI's Docs job and `make validate`'s reference check.
