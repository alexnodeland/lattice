# ADR-0002: DSPy judges and decision models as equals

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Two kinds of evaluator are wanted, honored equally:

- **DSPy judges**, optimized with GEPA (DSPy's reflective optimizer, which learns from textual feedback).
- **TypeSafe's Jev**, a "System One" decision model that returns typed answers (choices, scores, yes/no) with calibrated probabilities, in tens to hundreds of milliseconds.

pydantic-ai 2.51 supports decision models natively. `Agent('typesafe:jev-latest', output_type=...)` turns the output type's fields into questions. It raises `UnsureRoute` or `UnfillableRoute` when it should hand a step to a language model, which `FallbackModel` does.

## Decision

- **`DspyJudge`** builds a DSPy signature from the input and verdict types. It is optimized with **GEPA**, with people's reasons as textual feedback, and versioned by a hash of its program.
- **`DecisionEvaluator`** is a pydantic-ai agent on a decision model with the verdict type as output. A `FallbackModel` hands unsure or unfillable steps to a language-model judge. It is calibrated by tuning decision thresholds on the same datasets.
- Both implement one protocol, record their version on every verdict, and are measured with the same agreement metrics.

## Options considered

| Option | Latency and cost online | Explains itself | Learns from feedback |
|---|---|---|---|
| **Both kinds, with a fallback (chosen)** | Low (decision model first) | When it hands off | GEPA; threshold calibration |
| DSPy judges only | High | Yes | GEPA |
| Decision models only | Low | No | Threshold calibration |

## Consequences

- Easier: online evaluation is cheap, and the expensive judge runs only where the decision model is unsure.
- Harder: two kinds of evaluator to keep behaviorally comparable; the shared metrics make it measurable.

## Action items

1. [ ] Implement RFC-0001 phases 2 and 3.
