# ADR-0010: MIT license

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

relayr is combined with artifactr, reflexr and evalr in every application that uses it, and all three are MIT ([artifactr ADR-0016][a-adr-0016], [reflexr ADR-0014][r-adr-0014]). The repository was created with an MIT `LICENSE`.

## Decision

relayr is released under the **MIT License**, with the repository's `LICENSE` file (copyright 2026 Alex Nodeland), declared in `pyproject.toml` with `license = "MIT"` and `license-files`. Contributions are accepted under the same license.

## Consequences

- Easier: relayr can be used in any application, beside the libraries, with no license questions.

[a-adr-0016]: https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0016-mit-license.md
[r-adr-0014]: https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0014-mit-license.md
