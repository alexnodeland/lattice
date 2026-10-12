# ADR-0013: ty replaces pyright, with its stopgaps in one configuration

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#ci-and-tooling) replaces pyright with ty, configured once at the root: every rule an error (`all = "error"`), and `respect-type-ignore-comments = false`. Its adoption pull request runs both checkers once and reports what pyright strict catches that ty doesn't, and the family decides then whether any gap needs a stopgap ([Unresolved questions](../stackr/rfcs/0003-one-repository-lattice.md#unresolved-questions)).

Until now, each project had its own `[tool.pyright]`: strict for `src/` and `scripts/`, standard for `tests/`, and a `typings/` of stubs in artifactr, reflexr and evalr, partly the same stubs twice.

ty 0.0.86 with every rule an error, over every project's Python, found 406 diagnostics on code that pyright passed. Three things decide what to do with them:

- **One configuration can't give each project its own `tests` package.** Every package's tests import their helpers as `tests`, and run from the root, ty named each file from the repository's root (`packages.evalr.src.evalr`), so one class was two.
- **`all = "error"` turns on ty's opinions.** Two families made 152 of the 406: a truth test of an optional value (`if os.environ.get("X")`, where an empty value means unset too), and an assignment, return or yield of an `Any`, which SQLAlchemy's `Mapped[str] = mapped_column()` makes on every column.
- **ty is beta.** On a probe, a frozen dataclass's type parameter is covariant and a frozen Pydantic model's is invariant, and a set literal is inferred from its parameter's type in a call but not in a class keyword argument. pyright accepts both, and so does Python.

## Decision

- **ty checks every project, from the root's `[tool.ty]`.** Its roots are each project's `src/`, so modules have their own names; each project's `typecheck` task adds the project's own directory as a root too (`--config "environment.root = ['src', '.']"`), so its tests import as `tests`. docplan's and oncall's tests become a `tests` package, as the packages' are, and import `tests.conftest`. A root test fails if a project's `src/` is missing from the roots.
- **Every rule is an error, and only `ty: ignore` could silence one,** which the quality test now bans with the others; it also reads the stubs. `respect-type-ignore-comments = false`.
- **Four rules are off,** each with its reason in the configuration: `truthiness-test-of-none-union`, `unsound-assignment`, `unsound-return-statement` and `unsound-yield`.
- **Seven overrides turn one rule off in the files that meet one gap in ty,** each named beside its files: class keyword arguments (13 files), frozen Pydantic models' variance (13), pydantic-graph's builder (2), a variable declared `Any` (1), a generic model subscripted at run time (2), a type parameter's default class (1), and pydantic-ai's `Agent` overloads (1). Each goes when ty closes its gap.
- **The stubs live once, in the root's `typings/`,** as ty's `extra-paths`: evalr's DSPy stubs (artifactr's were a subset), artifactr's opentelemetry stubs (reflexr's were the same), and the rest. ty checks them, as part of the root's `typecheck`.
- **What ty found, the code fixes:** `@override` on every override (78), context managers' generators typed as generators (24), a `__name__` read from any callable (evalr's `FunctionEvaluator`, which a `functools.partial` would have broken), a method replaced on a protocol's instance (now `monkeypatch`), a dictionary unpacked into keyword parameters, and four `callable()` tests that are now `isinstance()` tests.
- **pyright goes:** from every dependency group, every `pyproject.toml`, the tasks and the hooks. The dev container runs ty's extension as the language server.

## What pyright strict catches that ty doesn't

Both ran once over the same code, pyright with every file strict and ty with every rule an error. `src/` and `scripts/` were already strict-clean, so pyright's findings are in `tests/`:

| pyright strict | Findings | ty on the same line |
|---|---|---|
| `reportUnknownArgumentType`, `…VariableType`, `…MemberType`, `…LambdaType`, `…ParameterType` | 160 | 1 |
| `reportUnusedClass`, `reportUnusedFunction`, `reportUnusedVariable` | 20 | 0 |
| `reportPrivateUsage` | 14 | 0 |
| `reportMissingTypeStubs` | 3 | 0 |
| `reportConstantRedefinition` | 2 | 0 |
| `reportArgumentType`, `reportMissingParameterType` | 2 | 0 |

The gap that matters is the first row. pyright strict kept an unknown type from spreading through `src/`, and ty has no rule for it: its `unsound-*` rules are the nearest, and they are off, since they also reject an explicit `Any`. With them on, `src/` has 66 findings, 40 of them SQLAlchemy columns. ruff's `SLF001` would cover private usage, which no one has asked for. No stopgap is added here: the family decides whether to turn the `unsound-*` rules on for `src/` with the columns left out.

## Options considered

| Option | What it costs |
|---|---|
| **ty, with every rule an error and its stopgaps in the configuration (chosen)** | Four rules off, and seven overrides to remove as ty closes its gaps |
| ty, with code changed until nothing is left out | Correct code made worse for a beta checker: casts at every column, and literal types spelled out at every class keyword |
| ty, and pyright strict for `src/` until ty catches unknown types | Two checkers, two configurations, and two sets of stubs |
| Wait for ty's first stable release | pyright per package, and seven configurations, for longer |

## Trade-off analysis

ty's own finds are worth having: the overrides and generators were missing on code pyright strict passed, and one was a bug. Its false positives sit in configuration, which review sees and a test keeps honest, rather than in the code as casts or suppressions. The cost is the unknown-type check that pyright strict gave `src/`, which is now the family's call.

## Consequences

- Easier: one type checker, one configuration and one set of stubs for every project; ty checks every project in seconds.
- Harder: an unknown type can spread through `src/` unflagged, until the family turns on the `unsound-*` rules there or ty gains a rule like pyright's.
- Harder: in an editor, which reads the root's configuration alone, a test's `from tests.… import` doesn't resolve.
- To revisit: each override with each ty release, and the `unsound-*` rules for `src/`.
