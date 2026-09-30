# ADR-0015: Quality gates

**Status:** Accepted, amended by [ADR-0052](0052-artifactr-in-lattice.md)
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

artifactr is a library other projects build on, and its core promise is that every surface behaves identically. Regressions in shared code spread to every downstream project. Trunk-based development ([ADR-0014](0014-trunk-based-development-with-rfcs-and-adrs.md)) only works if CI can be trusted to keep `main` releasable.

## Decision

CI enforces these gates on every pull request and on `main`:

| Gate | Rule |
|---|---|
| Coverage | **100% branch coverage** of the library package, `src/artifactr` |
| Types | pyright **strict** for `src/`, standard for `tests/` |
| Lint and format | ruff, with Google-style docstrings on public API |
| Tests | pytest with **warnings as errors**, on Python 3.12, 3.13 and 3.14 |
| Lockfile | `uv sync --locked`: CI fails if `uv.lock` is out of date |

Scope and exclusions:

- The coverage gate applies to the library. The reference implementation in `examples/` is covered by smoke tests; an interactive terminal client is not meaningfully unit-testable to 100%.
- The only coverage exclusions are configured centrally in `pyproject.toml`: `if TYPE_CHECKING:` blocks, `Protocol` class bodies, `@overload` stubs, `assert_never` calls, and `...` bodies. Inline `pragma: no cover` comments are not allowed.
- Core behaviour is additionally specified by conformance fixtures ([ADR-0001](0001-python-library-with-sans-io-core.md)).
- SQL storage is dialect-neutral in v0.1, so the whole storage suite can reach 100% on SQLite. CI also runs the same suite against PostgreSQL for correctness.

## Options considered

### Option A: 100% branch coverage of the library, strict types (chosen)

| Dimension | Assessment |
|---|---|
| Cost | Medium: every branch needs a test |
| Regression protection | High |
| Design pressure | Positive: unreachable code gets deleted |

**Pros:** no untested code paths in a library others depend on; the gate is binary and unambiguous.
**Cons:** some tests exist only to reach defensive branches; those branches should be questioned first.

### Option B: A lower threshold (for example 90%)

| Dimension | Assessment |
|---|---|
| Cost | Lower |
| Regression protection | Medium: which 10% is untested drifts over time |
| Design pressure | Weak |

**Pros:** cheaper.
**Cons:** the uncovered code tends to be the error handling that matters most.

### Option C: Line coverage only

| Dimension | Assessment |
|---|---|
| Cost | Lower |
| Regression protection | Misses untaken branches |
| Design pressure | Weak |

**Pros:** easier to reach.
**Cons:** an `if` without its `else` path looks fully covered.

## Trade-off analysis

For a library whose value is behavioural consistency, the cost of full branch coverage is paid once per change and repaid every time someone refactors safely. Strict typing catches a different class of error (the exhaustiveness of event and command handling) that tests alone cover poorly.

## Consequences

- Easier: refactoring with confidence; reviewing PRs, since untested code cannot merge.
- Harder: defensive code needs a test or needs to go.
- Revisit the Python version matrix as versions reach end of life.

## Action items

1. [x] Configure coverage, pyright, ruff and pytest in `pyproject.toml`.
2. [x] Add the CI workflow with the Python version matrix.
3. [x] Add the PostgreSQL job when SQL storage lands (RFC-0001 phase 4).
