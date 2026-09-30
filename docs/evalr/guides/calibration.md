# Calibration

A decision model is not trained; its thresholds are. A [decision evaluator](decision-evaluators.md) has two: `boolean_threshold`, the probability of yes at which a yes-or-no field is yes, and `min_confidence`, the confidence below which it hands off. `ThresholdCalibration` fits both to people's verdicts, as an optimizer, the same way [GEPA](dspy-judges.md#training-with-gepa) fits a DSPy judge ([ADR-0008](../adr/0008-decision-only-views-and-hand-off-by-composition.md)).

It needs the `jev` extra. The examples on this page use the `Thread` and `Helpfulness` types from [Getting started](../getting-started.md#1-define-the-types), and a [dataset](datasets.md) of threads with people's verdicts.

## Calibrating a decision evaluator

```python
from evalr import optimize
from evalr.decision import DecisionEvaluator, ThresholdCalibration

train, validate = dataset.labelled().split(0.3)

decider = DecisionEvaluator(Helpfulness, inputs=Thread, model="typesafe:jev-1.13.0")
calibrated = await optimize(
    decider,
    train=train,
    validate=validate,
    optimizer=ThresholdCalibration(target_agreement=0.9),
)
print(calibrated.boolean_threshold, calibrated.min_confidence)
```

The evaluator you started from is unchanged. The calibrated one is a copy with the new thresholds, and a new version when they differ. Calibrate against a pinned model, such as `typesafe:jev-1.13.0`: thresholds fitted to one model's probabilities say little about another's, and `jev-latest` can change.

## How it works

pydantic-ai applies a decision model's thresholds on the client, after the one request. So calibration asks the model once per example and then re-reads its answers under every candidate threshold, 0.05 to 0.95 in steps of 0.05 by default (`grid=`), without asking again:

1. **The boolean threshold** is the one at which the yes-or-no fields agree best with people on the training examples. Ties go to the threshold nearest the current one. A verdict type with no yes-or-no fields keeps its threshold.
2. **The hand-off threshold** is the lowest at which the evaluator agrees with people on at least `target_agreement` (0.9 by default) of the training examples it keeps, handing off the rest. No threshold at all is tried first, so an evaluator that already agrees well enough hands off nothing. If no threshold reaches the target, calibration takes the one that agrees best.

Agreement here is [per-field agreement](metrics.md#one-pair-of-verdicts), averaged over the examples kept. Examples that pydantic-ai hands off whatever the thresholds are left out of the fitting.

## Agreement against coverage

A higher hand-off threshold keeps fewer examples, and those it keeps are the ones the model is surest of, so agreement rises as coverage falls. What the evaluator hands off goes to its [fallback](decision-evaluators.md#hand-off-and-fallback), usually a language-model judge that is slower and costlier. `target_agreement` is where you choose the trade: the agreement you need from the decision model on what it keeps.

The calibrated evaluator's `Training` record shows both sides:

```python
training = calibrated.training
assert training is not None
print(training.score_before, training.score_after)
print(training.results)
```

- `score_before` and `score_after` are the agreement with people on the validation examples the evaluator keeps, with its old thresholds and its new ones. Each is measured over the examples it keeps, so their denominators differ.
- `results` holds what calibration found: `boolean_threshold`, `min_confidence`, and the share of validation examples kept before and after (`coverage_before`, `coverage_after`).

To judge the whole arrangement rather than the decision model alone, [measure](metrics.md#measuring-an-evaluator) the composition on the validation set: `measure(Fallback(calibrated, judge), validate)` reports agreement over every example, and latency and cost for each of the two evaluators.

## Options

| Option | Default | Meaning |
|---|---|---|
| `target_agreement` | 0.9 | The agreement, from 0 to 1, the evaluator should reach on what it keeps |
| `grid` | `DEFAULT_GRID`: 0.05 to 0.95 | Candidate thresholds, each strictly between 0 and 1 |
| `max_concurrency` | 4 | How many examples are asked at once |

Calibration is not the same as the [calibration metrics](metrics.md#calibration): the metrics measure whether an evaluator's confidence matches how often it is right; `ThresholdCalibration` chooses what the evaluator does with that confidence.
