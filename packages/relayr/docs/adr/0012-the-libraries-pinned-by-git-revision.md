# ADR-0012: The libraries pinned by git revision

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

relayr depends on artifactr (distributed as `artifactr-ai`) and reflexr. The family installs its libraries from GitHub by commit, not from PyPI, while publishing waits on a decision ([artifactr #23][a-23]), and stackr's template pins artifactr and reflexr only, letting evalr come with them at the commit their own sources pin ([stackr ADR-0013][s-adr-0013]).

## Decision

- **`pyproject.toml` requires `artifactr-ai` and `reflexr` by version**, and `[tool.uv.sources]` pins each to a commit on its `main`.
- **evalr has no pin of its own.** relayr requires no extra that needs it, and an application that installs the libraries' `[evals]` or `[langfuse]` extras gets evalr at the commit their sources pin.
- **A pin moves in its own pull request**, to the library's latest `main` or a named commit, with `uv lock` and the full gates, so a failure points at the library that moved.

## Consequences

- Easier: relayr is built and tested against exactly the commits it names, as the template's applications are.
- Harder: a fix in either library reaches relayr only when its pin moves, and when the libraries pin different evalr commits, `uv lock` fails and names both.
- Revisit when the libraries are published, which would replace the revisions with version ranges.

[a-23]: https://github.com/alexnodeland/artifactr/issues/23
[s-adr-0013]: https://github.com/alexnodeland/stackr/blob/main/docs/adr/0013-how-the-template-pins-the-libraries.md
