# ADR-0009: Quality gates

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

relayr's guarantees are its reason to exist: an event bridged exactly once, a proposal made once however often a run retries, and loops that end. They hold only as far as the tests that pin them, and trunk-based development ([ADR-0008](0008-trunk-based-development-with-rfcs-and-adrs.md)) only works if CI can be trusted. Its siblings hold themselves to the same bar ([artifactr ADR-0015][a-adr-0015], [reflexr ADR-0013][r-adr-0013]).

## Decision

CI enforces these gates on every pull request and on `main`, the same as the siblings':

| Gate | Rule |
|---|---|
| Coverage | **100% line and branch coverage** of `src/relayr` |
| Types | pyright **strict** for `src/` and `scripts/`, standard for tests, with **no inline suppressions** |
| Lint and format | ruff, with Google-style docstrings on public API |
| Tests | pytest with **warnings as errors**, on Python 3.12, 3.13 and 3.14, plus a PostgreSQL job once the ledger's SQL adapter exists |
| Lockfile | `uv sync --locked` |
| Docs | The site builds in strict mode, and its lists render |

The only coverage exclusions are configured centrally in `pyproject.toml` (`if TYPE_CHECKING:`, `Protocol` bodies, `@overload`, `assert_never`, `...`). `tests/test_quality.py` fails on any inline suppression: no `# type: ignore`, `# pyright: ignore`, `# noqa` or `# pragma: no cover`. Where a third-party library is untyped, a stub under `typings/` is preferred to a suppression.

## Consequences

- Easier: refactoring, and moving the libraries' pins, with confidence; untested code cannot merge.
- Harder: defensive code needs a test or needs to go.

[a-adr-0015]: https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0015-quality-gates.md
[r-adr-0013]: https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0013-quality-gates.md
