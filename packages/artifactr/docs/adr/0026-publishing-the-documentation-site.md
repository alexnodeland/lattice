# ADR-0026: Publishing the documentation site from main

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[ADR-0023](0023-documentation-site.md) built the documentation site but left publishing to the maintainer: its workflow deployed to GitHub Pages only when run by hand. The maintainer has now decided to publish it at `https://artifactr.alexnodeland.com`, with the repository public.

The documentation is evergreen: it changes in the same pull request as the code it describes. A site that is deployed only when someone remembers to run a workflow falls behind `main`, and readers can't tell that it has.

## Decision

- **Every push to `main` deploys the site.** `.github/workflows/docs.yml` runs on pushes to `main` as well as by hand. The published site is always `main`'s documentation, built in strict mode as CI builds it.
- **The custom domain is set in the repository's Pages settings**, with GitHub Actions as the source. Deployments from a workflow ignore a `CNAME` file, so the repository has none. `site_url` in `mkdocs.yml` is the custom domain, so canonical links and the sitemap point there.
- **The site shows `main`, not a release.** Until there are several releases with differing APIs, one version of the documentation is enough.

## Options considered

| Option | Site matches `main` | Effort per change |
|---|---|---|
| **Deploy on every push to `main` (chosen)** | Always | None |
| Deploy by hand (ADR-0023) | Only after someone runs it | A manual step each time |
| Deploy on releases only | At each release; ahead of released code in between | None, but guides for unreleased features stay unpublished |

## Consequences

- Easier: a merged documentation change is live within minutes.
- Harder: the site can describe features that are on `main` but not in the latest release. Revisit with versioned docs (for example, one site per minor version) when that gap matters.
- The workflow's `pages` concurrency group lets deployments queue rather than overlap.

## Action items

1. [x] Deploy on pushes to `main`, and point `site_url`, the project URLs and the README at the custom domain.
2. [ ] Consider versioned documentation once there are several releases.
