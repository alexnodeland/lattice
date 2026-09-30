# ADR-0001: Python library with a sans-IO core

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

artifactr's rules (validating edits, checking versions, applying patches, deciding what the agent should be told) must behave identically on every surface: agent tools, WebSocket, REST, MCP. Other host languages may follow later, and correctness of those rules matters more than raw speed.

A Rust core behind Python bindings was considered for exactly these reasons: exhaustive enums, one implementation shared across languages, and performance. Against that:

- v1 ships a Python host only. Types are defined as Pydantic models, and the agent runtime is pydantic-ai.
- Runtime cost is dominated by model latency; a faster store would not be felt.
- A binding boundary forces every value across as JSON. The Rust side could only validate against a JSON Schema exported from Pydantic, which drops custom validators and Pydantic's coercion rules, so data would be validated twice with subtly different semantics.

## Decision

artifactr is pure Python. Its rules live in `artifactr.core`, a **sans-IO** package:

- synchronous functions over immutable values: `commit`, `respond`, `change_notes`, `resume`
- no I/O, no `async`, no pydantic-ai import
- hosts load state, call core, and persist the result in their own transaction

Correctness comes from Python's type system used strictly: closed discriminated unions, `match` with `assert_never`, and pyright in strict mode. Portability comes from a conformance suite of JSON fixtures that specifies core's behaviour independently of the language. Native extensions are reserved for hot paths that measurement proves exist.

## Options considered

### Option A: Python with a sans-IO core (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Correctness | Strong with pyright strict; no compile-time guarantee outside it |
| Multi-language reach | Via conformance fixtures and a future port |
| Fit with Pydantic and pydantic-ai | Native |

**Pros:** one language; Pydantic validation end to end; simple debugging and packaging; the rules stay in one pure place.
**Cons:** a second host language means porting core; exhaustiveness depends on the type checker.

### Option B: Rust kernel behind PyO3 (and napi-rs later)

| Dimension | Assessment |
|---|---|
| Complexity | Medium to high: wheels per platform, two toolchains |
| Correctness | Compile-time exhaustiveness in the kernel |
| Multi-language reach | High |
| Fit with Pydantic and pydantic-ai | Poor at the boundary: JSON-only values, double validation |

**Pros:** one kernel for every language; exhaustive enums.
**Cons:** the boundary is awkward for exactly the types that matter; contributors need Rust; the reference is harder to read in one sitting.

### Option C: Rust workspace engine (storage and log in Rust, async bindings)

| Dimension | Assessment |
|---|---|
| Complexity | High: async iterators and runtimes across the boundary |
| Correctness | High inside the engine |
| Multi-language reach | High |
| Fit with Pydantic and pydantic-ai | Poor, and the host cannot share a transaction with the engine's store |

**Pros:** more of the system under Rust's guarantees; performance headroom.
**Cons:** the hardest binding work; applications cannot write their own tables in the same transaction.

### Option D: Rust workspace server with a Python client SDK

| Dimension | Assessment |
|---|---|
| Complexity | High: two deployables |
| Correctness | High on the server |
| Multi-language reach | High: any client speaks the protocol |
| Fit with Pydantic and pydantic-ai | Good on the client side |

**Pros:** agents in any language are just clients.
**Cons:** turns a library into a service to operate, contradicting [ADR-0013](0013-library-with-reference-implementation.md).

## Trade-off analysis

The real benefit behind the Rust options was keeping every rule in one pure, portable place. The sans-IO design keeps that benefit without a binding boundary. What Rust would add on top (compile-time exhaustiveness, speed) is either largely available through strict typing or not needed at model-latency timescales. Its costs, double validation and async across the boundary, fall on exactly the code we most want to keep simple.

## Consequences

- Easier: Pydantic is the single source of truth for types; one toolchain; contributors need only Python.
- Easier: a later port, or a native hot path, is a local change checked by the fixtures.
- Harder: exhaustiveness is enforced by pyright rather than a compiler, so CI must run pyright strict.
- Revisit if a second host language becomes a real requirement, or profiling finds a hot path in core.

## Action items

1. [ ] Configure pyright strict for `artifactr.core`.
2. [ ] Define the conformance fixture format (given state and command, expect events or a rejection).
3. [ ] Run the fixtures in CI.
