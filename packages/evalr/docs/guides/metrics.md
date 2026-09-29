# Agreement and calibration metrics

An evaluator is useful to the extent that it says what people would have said. evalr measures that directly: **agreement** compares an evaluator's verdicts with people's, field by field, with the measure that suits each field's kind, and **calibration** asks whether its confidence means what it says. Both apply to every kind of evaluator, since all of them give verdicts of the same types.

The examples on this page use the `Thread` and `Helpfulness` types from [Getting started](../getting-started.md#1-define-the-types), and a [dataset](datasets.md) of threads with people's verdicts.

## Measuring an evaluator

`measure` judges every labelled example of a dataset and compares the evaluator's verdicts with people's:

```python
from evalr import measure
from evalr.decision import DecisionEvaluator

decider = DecisionEvaluator(Helpfulness, inputs=Thread)
measurement = await measure(decider, dataset)

print(measurement.agreement.score)
for field in measurement.agreement.fields.values():
    print(field.field, field.kind.value, field.n, field.score)
```

It prints the overall agreement, from 0 to 1, and each field's, such as:

```text
0.9166666666666666
rating ordinal 24 0.8333333333333334
resolved binary 24 1.0
```

A `Measurement` holds:

| Field | Holds |
|---|---|
| `evaluator`, `version` | What was measured |
| `dataset`, `dataset_version` | On what: the dataset's name and content hash |
| `verdicts` | The verdicts the evaluator gave, by example id |
| `errors` | What went wrong where it gave none, by example id |
| `agreement` | Agreement with people: overall, and per field |
| `calibration` | How well its confidence predicts being right, per field |
| `stats` | Latency and cost, per evaluator version that gave verdicts |

- **Only labelled examples count**, and an example the evaluator fails on, or hands off, counts as a missing prediction, so an evaluator cannot look better by declining hard inputs. `errors` says what happened.
- **A composition is measured as a whole**, and `stats` splits it: measuring `Fallback(decider, judge)` gives one agreement for the arrangement, and latency and cost for each of the two evaluators that gave verdicts.
- **Measure on examples the evaluator was not fitted to.** After [GEPA](dspy-judges.md#training-with-gepa) or [calibration](calibration.md), measure the validation split, or a fresh one.
- `max_concurrency` (4 by default) bounds how many examples are judged at once.

## Agreement

`agreement(expected, predicted, verdict_type=)` compares two sequences of verdicts pair by pair: people's, and an evaluator's for the same inputs, `None` where it gave none. `measure` calls it for you. The result has `n` (the pairs compared), `score` (the mean per-pair agreement, from 0 to 1), and one `FieldAgreement` per scored field, with the measures that suit its kind:

| Kind | Measures | On a missing prediction |
|---|---|---|
| binary, categorical | `accuracy`, and Cohen's `kappa`: agreement beyond what the two sides' label frequencies give by chance (1 is perfect, 0 is chance) | Counts as a wrong label |
| ordinal, numeric | `mean_absolute_error`, and `spearman`, the rank correlation with tied values given their average rank | Left out, and counted in `missing` |
| text | Not scored | |

Every field also has `n` (the pairs where people gave the field a value), `missing`, and `score`, its mean per-pair agreement. Fields people left empty do not count, so an optional field is measured only where people filled it.

A measure that is undefined for its data (no pairs; kappa when both sides always give one same label; Spearman when a side never varies) is `None`, not NaN, so results compare and serialize cleanly.

### One pair of verdicts

`field_agreement(expected, predicted)` scores one pair, field by field, from 0 to 1, and `agreement_score` is its mean. It is the metric GEPA trains judges to, and calibration fits thresholds to:

- Binary and categorical fields agree fully or not at all.
- Bounded numbers lose agreement in proportion to the distance over their range: `1 - |e - p| / (upper - lower)`. A rating of 2 against people's 4, on a scale of 1 to 5, agrees 0.5.
- Unbounded numbers agree `1 / (1 + |e - p|)`.
- A missing prediction, of the whole verdict or of a field, agrees not at all.

```python
from evalr.core import agreement_score, field_agreement

people = Helpfulness(rating=4, resolved=True)
judge = Helpfulness(rating=2, resolved=True, reason="Partly")

print(field_agreement(people, judge), agreement_score(people, judge), agreement_score(people, None))
```

```text
{'rating': 0.5, 'resolved': 1.0} 0.75 0.0
```

## Calibration

A verdict's confidence is one probability per field: that the field's value is right. Calibration measures whether it means that, for each field with confidence, over the verdicts that have one: `measurement.calibration`, or `calibration(expected, verdicts, verdict_type=)` directly.

```python
for field in measurement.calibration.values():
    print(field.field, field.accuracy, field.confidence, field.expected_calibration_error)
```

| Field | Holds |
|---|---|
| `n` | Pairs with a value from people and a confidence |
| `accuracy` | The share of those whose value was right |
| `confidence` | The mean confidence |
| `expected_calibration_error` | The gap between confidence and accuracy, averaged over ten bins of equal width, each weighted by its share of the pairs. 0 is perfect. |
| `brier_score` | The mean squared difference between confidence and being right. 0 is perfect; always answering with confidence 0.5 scores 0.25. |

Both are top-label measures: the confidence in the value given, against whether it was right. A well-calibrated evaluator's confidence matches its accuracy, which is what makes a [hand-off threshold](calibration.md) meaningful: at `min_confidence=0.8`, every field of a kept verdict is right at least about 80% of the time.

## Cost and latency

`evaluator_stats(verdicts)` summarizes verdicts per evaluator version: the count, the mean, median and 95th-percentile latency (by nearest rank), and the total and mean cost over the verdicts that report one (`None` if none do). `measurement.stats` is its result for the measured verdicts. DSPy judges report no cost; decision evaluators report pydantic-ai's.

## The measures on their own

The measures over paired values are plain functions, for data that did not come from verdicts:

```python
from evalr.core import brier_score, cohen_kappa

print(cohen_kappa([True, True, False, False], [True, False, False, False]))
print(brier_score([0.9, 0.6], [True, False]))
```

```text
0.5
0.185
```

| Function | Measures |
|---|---|
| `accuracy(expected, predicted)` | The share of equal pairs |
| `cohen_kappa(expected, predicted)` | Cohen's kappa |
| `mean_absolute_error(expected, predicted)` | The mean absolute difference |
| `spearman(expected, predicted)` | Spearman's rank correlation |
| `brier_score(confidences, correct)` | The Brier score |
| `expected_calibration_error(confidences, correct, bins=10)` | Expected calibration error over equal-width bins, each closed below, the last including 1 |

The measures are property-tested against scikit-learn and SciPy, and calibration error against a NumPy computation.

## Choosing between evaluators

`BestOf`, in `evalr.memory`, is an optimizer that trains nothing: it measures the evaluator you give it and each candidate on the training set, keeps the one that agrees best with people, and measures the choice on the validation set. It works for any kind of evaluator, so it can pick between a decision model, a judge and their composition:

```python
import dspy

from evalr import Fallback, optimize
from evalr.dspy import DspyJudge
from evalr.memory import BestOf

judge = DspyJudge(Helpfulness, inputs=Thread, lm=dspy.LM("openai/gpt-5-mini"))
unsure = DecisionEvaluator(Helpfulness, inputs=Thread, min_confidence=0.7)
candidates = BestOf([judge, Fallback(unsure, judge)])

train, validate = dataset.labelled().split(0.3)

chosen = await optimize(decider, train=train, validate=validate, optimizer=candidates)
print(chosen.name, candidates.measurements[-1].agreement.score)
```

A tie keeps the evaluator you gave, so a candidate must be strictly better to win. `measurements` holds every measurement taken, in order; the last is the choice's, on the validation set.
