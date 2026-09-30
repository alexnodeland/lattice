# ADR-0013: How the template pins the libraries

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

## Context

The libraries install from GitHub by commit, not from PyPI ([artifactr#23](https://github.com/alexnodeland/artifactr/issues/23)). [ADR-0011](0011-the-application-template-in-detail.md) made each pin a Copier question (`artifactr_rev`, `reflexr_rev` and `evalr_rev`). It also had an application declare evalr's source itself, on the premise that a dependency's own `[tool.uv.sources]` doesn't apply to its dependents. Its amendment made evalr follow reflexr's pin; with both `[langfuse]` extras now requiring evalr, it would have had to follow both.

Two things were wrong with that:

- **The application's evalr source was never needed.** uv resolves a library's requirements with the library's own sources, and a git URL one of them requires satisfies every other requirement on evalr, the application's own `evalr[langfuse]` included. An application requiring `artifactr-ai[langfuse]`, `reflexr[langfuse,evals]` and `evalr[langfuse]`, with sources for the two libraries only, locks evalr at the commit both pin, and so does every variant of the template. When the two pin different commits, `uv lock` fails and names both URLs. So a pin of the template's own could only repeat theirs, or break the lock.
- **Answers held the pins back.** Copier records answers and reuses them on `copier update`. An application kept the revisions it was generated with while the template's code moved on, which is the one combination no check ever runs: newer template code on older libraries.

## Decision

- **The template pins artifactr and reflexr, and nothing else.** The generated `pyproject.toml`'s `[tool.uv.sources]` names the two libraries. evalr comes with them, at the commit their own sources pin. An application with evals still requires `evalr[langfuse]`, since it imports evalr, but declares no source for it.
- **The pins are the template's values, not questions.** `artifactr_rev` and `reflexr_rev` in `copier.yml` have `when: false` and no validator. They are never asked and never recorded in `.copier-answers.yml`, so `copier update` moves them with the template code written for them. An application that holds a library back edits its rev in `pyproject.toml`; Copier's three-way merge keeps the edit, and marks a conflict when an update changes that line or one beside it, such as the other library's pin.
- **`make bump-libraries` moves artifactr and reflexr** to their `main`, or to a named revision, and doesn't look at evalr. When the libraries' evalr pins differ, `uv lock` fails in the pull request's Template jobs, naming both.

This supersedes the revisions in ADR-0011's Questions bullet, its bullet on pinning the libraries by git revision, and the "evalr follows reflexr" bullet of its amendment on `make bump-libraries`. The rest of that amendment (the script, `--check`, and a person opening the pull request) stands, for the two libraries.

## Options considered

| Option | evalr's pin | An application's pins on `copier update` |
|---|---|---|
| **The template's values; evalr from the libraries (chosen)** | The libraries', once | Move with the template's code |
| Questions, and evalr's source declared too (ADR-0011) | Repeated, and must match the libraries' | Stay where they were generated |
| Questions, and evalr from the libraries | The libraries', once | Stay where they were generated |

## Consequences

- Easier: evalr is pinned in one place, the libraries. An updated application runs the libraries its template code was written and checked against, and the bump script has two libraries to move.
- Harder: holding a library back is an edit to `pyproject.toml`, which a later `copier update` that moves either pin marks as a conflict.
- Revisit: published releases of the libraries, which would replace git revisions with version ranges.
