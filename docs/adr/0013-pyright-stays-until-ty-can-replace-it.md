# ADR-0013: pyright stays until ty can replace it

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#ci-and-tooling) replaces pyright with ty in phase 6: one configuration at the root, every rule an error (`all = "error"`), and `respect-type-ignore-comments = false`. Its adoption pull request was to run both checkers once and report what pyright strict catches that ty doesn't, and the family would decide then whether any gap needs a stopgap ([What ty misses](../stackr/rfcs/0003-one-repository-lattice.md#unresolved-questions)).

That pull request, [#58](https://github.com/alexnodeland/lattice/pull/58), ran ty 0.0.86 over every project:

- **ty found 406 diagnostics on code that pyright passes.** About a quarter were real: 78 overrides without `@override`, 24 context managers whose generators were typed as iterators, and a bug, evalr's `FunctionEvaluator` reading `__name__` from any callable, which a `functools.partial` doesn't have.
- **Green needed four rules off and seven per-file overrides.**
  - Two families made 152 of the diagnostics: `truthiness-test-of-none-union` (`if os.environ.get("X")`, where an empty value means unset too), and the three `unsound-*` rules, which reject any `Any`, SQLAlchemy's `Mapped[str] = mapped_column()` among them.
  - The overrides cover gaps in ty, two of them confirmed on a minimal probe: a frozen Pydantic model's type parameter is invariant, where a frozen dataclass's is covariant, and a class keyword argument isn't inferred from its parameter's type.
- **ty flagged 1 of pyright strict's 202 findings.** With every file strict, pyright found 160 unknown types spreading (`reportUnknown*`), 20 unused classes, functions and variables, 14 private usages and 8 others, all in `tests/`, since `src/` is strict-clean. ty has no rule that keeps an unknown type out of `src/`. Its `unsound-*` rules are the nearest, and they also reject an explicit `Any`.
- **One configuration can't give each project its own `tests` package.** Every package's tests import their helpers as `tests`, so each project's check had to add its own directory as a root on the command line.

## Decision

- **pyright strict stays the gate,** per project as today: strict for `src/` and `scripts/`, standard for `tests/`. ty is not adopted.
- **ty's real findings are kept,** fixed in code that pyright also accepts ([#62](https://github.com/alexnodeland/lattice/pull/62)): `@override` on every override, the stubs included; context managers' generators typed as generators; evalr's `FunctionEvaluator` names a callable without a `__name__` for its type, with a test; a method replaced on a protocol's instance in a test is now replaced with `monkeypatch`; a dictionary unpacked into keyword parameters is passed as keywords; a redundant cast is gone; and the DSPy stub's `Example(base, /, **kwargs)` is positional-only, as DSPy's own calls use it.
- **ty is tried again when it has a strict mode and catches what pyright strict does on this code:** the same run, both checkers over every project, with no rule off and no override for a gap in ty.

This amends RFC-0003's Types row and answers its "What ty misses".

## Options considered

| Option | What it costs |
|---|---|
| **pyright strict, and ty later (chosen)** | Seven per-project configurations and three sets of stubs, as today |
| ty, with four rules off and seven overrides | The unknown-type check on `src/` is lost, and the overrides hide every argument check in 29 files |
| ty and pyright strict together | Two checkers, two configurations, and two answers to every finding |

## Trade-off analysis

ty's own finds were worth having, and the code keeps them. As the gate, it would lose what pyright strict gives `src/`, the check that no unknown type spreads through it, and it would need holes in its configuration for its own gaps. pyright costs nothing to keep, and ty's next release can be tried with the same run.

## Consequences

- Easier: nothing changes for contributors. pyright strict is the gate, and the code no longer misses an override or mistypes a context manager.
- Harder: each project keeps its own `[tool.pyright]`, and artifactr, reflexr and evalr keep their own stubs.
- To revisit: ty with each release that brings a strict mode, using the same comparison.
