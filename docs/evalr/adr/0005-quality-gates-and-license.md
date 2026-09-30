# ADR-0005: Quality gates and license

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

evalr decides which agents, prompts and models are better. Its metrics and evaluators must be as trustworthy as the libraries they judge, whose gates are 100% branch coverage, pyright strict with no suppressions, and warnings as errors ([artifactr ADR-0015](https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0015-quality-gates.md), [reflexr ADR-0013](https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0013-quality-gates.md)).

## Decision

- **The same gates as its siblings:**
  - 100% line and branch coverage of `src/evalr`
  - pyright strict for `src/`, with no inline suppressions
  - ruff with Google-style docstrings
  - pytest with warnings as errors, on Python 3.12, 3.13 and 3.14
  - a locked `uv.lock`
- **No network in tests:** Jev through the SDK's transport, DSPy through its dummy language model, Langfuse through an in-memory exporter and fakes, and Hugging Face through local datasets.
- **Metrics are property-tested** against reference implementations.
- **MIT license,** as in artifactr and reflexr.

## Consequences

- Easier: an evaluation result can be trusted as far as the tests reach, which is everywhere.
- Harder: every integration needs a test seam; the evaluator kinds are chosen partly because they have one.

## Action items

1. [x] Configure the gates and CI (RFC-0001 phase 0).
