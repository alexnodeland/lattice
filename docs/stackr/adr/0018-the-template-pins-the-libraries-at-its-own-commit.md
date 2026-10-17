# ADR-0018: The template pins the libraries at its own commit

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Supersedes [ADR-0013](0013-how-the-template-pins-the-libraries.md), and [ADR-0011](0011-the-application-template-in-detail.md)'s amendment on `make bump-libraries`. Amends [ADR-0016](0016-stackr-in-lattice.md), when Template and Smoke run, and [lattice ADR-0002](../../adr/0002-ci-runs-every-affected-project-and-its-dependents.md), which kept them on `moon ci`.

## Context

ADR-0013 pinned artifactr and reflexr each to a commit of its own repository, as hidden values in `copier.yml` that `make bump-libraries` moved, and evalr came with them at the commit their own sources pinned. lattice holds the template and the libraries in one repository, and those pins still named the old repositories, which are frozen. A pull request that changed a library and the template together generated applications on the old libraries, so it couldn't pass the Template job until a second pull request moved the pins. [Lattice RFC-0001](../../rfcs/0001-grantr-identity-and-access.md), grantr, changes artifactr's and reflexr's `Authorize` hook and the template's code that implements it in one pull request.

[RFC-0003](../rfcs/0003-one-repository-lattice.md#stackrs-template-from-inside-lattice) designed the replacement (its D4): pin every library at the commit the template is rendered from, and render the template in CI with path sources to the checkout. Building it found two things the design didn't say:

- **Path sources must be editable.** Each library's own `evalr = { workspace = true }` becomes an editable path to the checkout's evalr, so an application's evalr line must be editable too, or uv sees two sources for one package and refuses to lock (uv 0.12.12).
- **The smoke test's application builds in Docker,** from a context that holds only the application. A path to the checkout doesn't exist in that build, and making it exist would add a build context and a copy of the checkout to the template's `compose.yaml` and `Dockerfile`, for CI's sake only.

## Decision

- **An application installs the libraries from lattice at the commit it was rendered from.** The generated `pyproject.toml`'s `[tool.uv.sources]` names `https://github.com/alexnodeland/lattice`, with each library's `subdirectory`, at `_copier_conf.vcs_ref_hash`: artifactr's and reflexr's lines for the libraries it uses, and evalr's when it has evals. uv makes each library's `evalr = { workspace = true }` the same repository and commit, so evalr is one package at one commit.
- **`copier.yml` holds no revision.** `artifactr_rev` and `reflexr_rev` go, and `copier update` moves the template's code and the libraries together, to the combination lattice's CI checked together. To try another commit, an application changes every `rev`; when two lines disagree on evalr, `uv lock` fails, naming both.
- **`libraries_path`, a hidden value, installs them from a checkout instead.** Set to lattice's `packages/` directory, it makes each source `{ path = "<libraries_path>/<package>", editable = true }`. `scripts/check-app`, CI's Template job, sets it, so the job checks the pull request's libraries with its template, working tree included.
- **The smoke test's application installs from GitHub at `HEAD`,** as an application generated from lattice does. In CI, `HEAD` is the pull request's merge commit, which GitHub serves, so the application runs the pull request's libraries. Locally, `make smoke-app` needs `HEAD` pushed and the working tree clean: Copier renders uncommitted changes from a commit of its own, which GitHub doesn't have.
- **Template and Smoke run through `scripts/affected.py`,** as Check, Tests and Images do (lattice ADR-0002), so a change to stackr or to any library it depends on runs them. The matrix values stay out of the tasks' inputs: moon counts a variable that is set as a change, and every variant would run on every pull request.
- **`scripts/bump-libraries` and `make bump-libraries` retire,** with the reference table of the template's pins.

## Options considered

| Option | A library and the template changed together | The smoke test's application | The template's files |
|---|---|---|---|
| **The rendered commit, with path sources in the Template job (chosen)** | Checked together in one pull request | The pull request's libraries, from its merge commit on GitHub | `pyproject.toml.jinja` only |
| Path sources in the Smoke job too (RFC-0003) | Checked together in one pull request | The pull request's libraries, from a copy of the checkout in the build | Also `compose.yaml.jinja` and `Dockerfile.jinja`, for CI alone |
| Revisions in `copier.yml`, moved by `bump-libraries` (ADR-0013) | Two pull requests: the library, then the pins and the template | The pinned libraries | `pyproject.toml.jinja` and `copier.yml` |

## Trade-off analysis

The rendered commit is the one choice in which an application gets exactly what lattice's CI checked, and it removes the pins and their script rather than moving them to a new repository. Path sources are what let the Template job check a library's change before it is on GitHub, and on a working tree with uncommitted changes. The Smoke job's application is the one place where a path can't reach, and there the merge commit already holds the pull request's libraries, so installing from it, as a user's application would, checks the same combination with no change to what the template generates.

## Consequences

- Easier: a pull request that changes a library and the template together passes the Template and Smoke jobs, and a library's change that breaks the template fails them.
- Easier: there are no pins to move, and an application can't run template code on libraries it wasn't checked with.
- Harder: a library-only pull request now runs the Template and Smoke jobs, which are the longest.
- Harder: `make smoke-app` fails locally unless `HEAD` is pushed and the working tree clean: Copier renders uncommitted changes from a commit of its own, which GitHub doesn't have. An application's `_commit` is `git describe --tags` of the nearest package tag, such as `evalr-v0.2.0-1-gf4e1841`, which updates read correctly but people may find confusing.
- Revisit: published releases of the libraries, which would replace the git sources with version ranges. *Every library has been on PyPI since 2026-10-17 ([lattice ADR-0023](../../adr/0023-publishing-to-pypi-from-the-release-workflow.md)); the template has not changed yet.*
