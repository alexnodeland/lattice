# ADR-0008: Decision-only views, and hand-off by composition

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

RFC-0001 left open how a decision evaluator treats free-text fields: pydantic-ai raises `UnfillableRoute` for them, and evalr would either derive a decision-only view of the verdict type or rely on the language-model fallback. It also sketched the fallback as pydantic-ai's `FallbackModel(decision_model, llm_judge_model, fallback_on=DecisionHandOff)`.

Building it against pydantic-ai 2.51 and TypeSafe's SDK 0.7.2 showed:

- A decision model accepts only some field types: `bool`; a `Literal` or `Enum` of two or more strings or whole numbers (optional or not); a rubric of whole numbers from 0, every level described; a `float` from 0 to an upper bound. A rating such as `Annotated[int, Field(ge=1, le=5)]`, free text, unbounded numbers and an optional `bool` are refused.
- With a single output type, a refused field is an error at request time, not `UnfillableRoute`. And there is no route question, so `UnsureRoute` never fires either: neither hand-off happens.
- The confidence pydantic-ai reports for a yes-or-no field is its distance from `decision_boolean_threshold`, not the probability that the answer is right.
- Thresholds are applied on the client, after the one request, so the same answers can be re-read under other thresholds without asking again.

And ADR-0006 made evaluators adapters of one port, composed rather than special-cased.

## Decision

- **A decision evaluator's output type is the verdict type's decision-only view** (`decision_view`):

  | Verdict field | In the view |
  |---|---|
  | `bool`, required | `bool` |
  | `Literal` or `Enum` of 2 to 255 strings or whole numbers | unchanged |
  | `int` bounded on both sides, 2 to 255 values | `Literal` of every value |
  | `float` from 0 to an upper bound, required | unchanged |
  | anything else, including text | left out |

  A field left out keeps its default in the verdict, so a required field the view would leave out is refused when the evaluator is built, with a message saying to give it a default or judge the type with a language model.

- **Confidence on a verdict is the probability that the value is right.** For a choice that is the model's probability of the choice; for a yes-or-no field, evalr recovers the model's probability of yes from pydantic-ai's threshold-relative confidence, and records the probability of the answer given.
- **The evaluator hands off by raising the core's `HandOff`**: when pydantic-ai raises `DecisionHandOff` (with routes or tools), and when any field's confidence is below the evaluator's `min_confidence`. Service failures are not hand-offs; they propagate.
- **The language-model fallback is a second evaluator, composed by the core's `Fallback`**: `Fallback(DecisionEvaluator(...), DspyJudge(...))`. The fallback judges the whole verdict type, including the text fields the view leaves out.
- **Calibration tunes `decision_boolean_threshold` and `min_confidence`** on a dataset, from one request per example.
- The evaluator's version hashes the model's name, the types, the instructions and both thresholds. The model that actually answered (`jev-1.13.0` for `jev-latest`) is recorded on the evaluation span, and calibrated evaluators should name a pinned model.

## Options considered

### Free-text and other fields a decision model cannot fill

| Option | Works with one output type | Fills text |
|---|---|---|
| **A decision-only view, the rest from a composed fallback (chosen)** | Yes | Yes, through the fallback |
| Rely on `UnfillableRoute` and the fallback | No: with one output type it is an error at request time | Only if the error were a hand-off |
| Require verdict types to be decision-only | Yes | No |

### Where the language-model fallback lives

| Option | The fallback sees | Composes with other evaluators |
|---|---|---|
| **The core's `Fallback` over two evaluators (chosen)** | The whole verdict type | Yes: any evaluator of the port |
| pydantic-ai's `FallbackModel` inside the agent | The same decision-only view: no text | No: only pydantic-ai models |

## Consequences

- Easier: any verdict type with defaults for its text fields works with a decision model unchanged, and the fallback judge fills what the model cannot.
- Easier: verdicts from both kinds of evaluator carry confidence with one meaning, so calibration metrics apply to both.
- Harder: evalr depends on how pydantic-ai reports yes-or-no confidence; a test pins the recovery against pydantic-ai's own numbers.
- Revisit: rubric questions (whole numbers from 0 with every level described) are not generated for ordinal fields yet; a rating is asked as a choice.

## Action items

1. [x] Implement `decision_view` and `DecisionEvaluator` (RFC-0001 phase 3).
2. [x] Implement threshold calibration (phase 3).
