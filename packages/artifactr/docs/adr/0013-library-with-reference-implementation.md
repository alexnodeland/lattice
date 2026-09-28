# ADR-0013: A library with adapters and a reference implementation

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

This repository started as a runnable backend meant to be copied and adapted. Copied templates diverge: each copy accumulates its own fixes and extensions, and improvements never flow back. The goal is an extendable framework whose abstractions downstream projects make concrete for their own artifact types.

## Decision

artifactr is a **library**:

- The `artifactr` distribution contains `core`, `workspace` and `agent`.
- Optional extras add integrations: `artifactr[sql]`, `artifactr[fastapi]` and `artifactr[mcp]`.
- Applications depend on it and extend it through artifact subclasses, pydantic-ai toolsets and capabilities, and the storage protocols.

`examples/docplan` is a **reference implementation** built only on the public API: a Markdown document and a structured plan, with the CLI. It is one implementation of the library, not the library itself, and it doubles as the end-to-end test.

The current prototype in `src/` is removed once `docplan` reaches parity.

## Options considered

### Option A: A library, adapters as extras, and a reference implementation (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Medium: a public API to design and version |
| Downstream maintenance | Low: upgrades flow through a dependency |
| Flexibility | Through defined extension points |

**Pros:** fixes reach every user; the reference implementation keeps the API honest.
**Cons:** the public API needs care and semantic versioning.

### Option B: A template to fork

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Downstream maintenance | High: every copy diverges |
| Flexibility | Total |

**Pros:** fastest start.
**Cons:** no shared improvements; the problem this ADR exists to solve.

### Option C: A specification with a thin reference implementation

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Downstream maintenance | High: each project implements the spec |
| Flexibility | Any stack |

**Pros:** language-neutral.
**Cons:** every consumer rebuilds the machinery.

## Trade-off analysis

Only Option A lets downstream projects share the hard parts (concurrency, the log, agent integration, transports) while customizing the parts that differ, which are the artifact types and tools. The conformance fixtures from [ADR-0001](0001-python-library-with-sans-io-core.md) keep Option C's language neutrality available if it is ever needed.

## Consequences

- Easier: a new application is a set of artifact types, tools, and a few lines of wiring.
- Harder: breaking changes need deprecation paths once the library has users.
- Revisit extras boundaries as integrations grow.

## Action items

1. [ ] Restructure `pyproject.toml`: remove the self-dependency, stop shipping `scripts/` in the wheel, declare the extras, set pytest's path to `src`.
2. [ ] Create `examples/docplan` and port the CLI to it.
3. [ ] Remove the prototype once `docplan` reaches parity.
