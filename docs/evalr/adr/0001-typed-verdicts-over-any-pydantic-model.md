# ADR-0001: Typed verdicts over any Pydantic model

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

artifactr and reflexr record typed feedback from people, as Pydantic models. Evaluators should predict the same types, so that they can be trained on people's feedback and measured against it. evalr must not import either library ([artifactr ADR-0029](https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0029-evalr-shared-eval-kit.md)).

## Decision

- An evaluator's verdict type is **any Pydantic model**. Field types determine how each field is judged and scored: bounded numbers, `bool`, `Literal` and `Enum`, and free-text `str`.
- The **`Evaluator[InputT, VerdictT]`** protocol returns a `Verdict[VerdictT]`: the value, per-field confidence, the evaluator's name and version, latency, cost and trace id.
- Inputs are Pydantic models, turned into text by formatters within a token budget.

## Options considered

| Option | Shared with the libraries | Typed |
|---|---|---|
| **Any Pydantic model (chosen)** | Structurally, with no import | Yes |
| An evalr `Verdict` base class the libraries subclass | Needs the libraries to depend on evalr | Yes |
| Untyped scores (name and number) | Trivially | No |

## Consequences

- Easier: an application's feedback type, a library's feedback type or an ad-hoc model all work as verdict types.
- Harder: field types must be judgeable. A free-text field can only be filled by a language-model judge.

## Action items

1. [x] Implement the core (RFC-0001 phase 1).
