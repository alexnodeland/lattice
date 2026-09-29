# Typed verdicts and field kinds

An evaluator's verdict is an instance of a Pydantic model: the **verdict type**. It is usually the same type people use to give feedback, so an evaluator predicts exactly what a person would have said, and the two can be compared field by field ([ADR-0001](../adr/0001-typed-verdicts-over-any-pydantic-model.md)). evalr needs nothing else from the type: an application's own model, a feedback type registered with artifactr or reflexr, or an ad-hoc model all work.

## A verdict type

```python
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class Topic(Enum):
    BILLING = "billing"
    BUG = "bug"
    OTHER = "other"


class Helpfulness(BaseModel):
    """Whether the reply helped the person."""

    rating: Annotated[int, Field(ge=1, le=5, description="How much the reply helped")]
    resolved: bool = Field(description="The request was fully addressed")
    topic: Topic = Field(default=Topic.OTHER, description="What the request was about")
    tone: Literal["warm", "neutral", "cold"] | None = None
    share_done: float = Field(default=1.0, ge=0.0, le=1.0, description="How much was done")
    reason: str | None = Field(default=None, description="Why, in a sentence")
```

The docstring says what the verdict is for, and each field's description is the instruction an evaluator reads for that field. Language-model judges see both; decision models turn each field into a question with the description as its text.

## Field kinds

The type of each field decides how it is judged and how it is scored. evalr calls this the field's **kind**:

| Field type | Kind | Filled by | Agreement with people | Score |
|---|---|---|---|---|
| `bool` | binary | any evaluator | accuracy, Cohen's kappa | `BOOLEAN` |
| `Literal`, `Enum` | categorical | any evaluator | accuracy, Cohen's kappa | `CATEGORICAL` |
| `int` bounded on both sides | ordinal | any evaluator | mean absolute error, Spearman | `NUMERIC` |
| any other `int` or `float` | numeric | any evaluator | mean absolute error, Spearman | `NUMERIC` |
| `str` | text | language-model judges only | not scored | `TEXT` |

A few rules complete the table:

- `X | None` is judged as `X`, and may be left empty. An empty field gives no score and is left out of agreement.
- Bounds come from `Field(ge=, le=, gt=, lt=)` or `annotated_types` constraints, at any level of `Annotated`, including inside an optional. An integer's exclusive bounds become inclusive: `gt=0` is a lower bound of 1.
- Anything else (a list, a nested model, a union of several types) cannot be judged. Evaluators, datasets and metrics raise `UnsupportedField` as soon as they are given such a type, rather than failing on the first input.

`verdict_fields` describes a type the way every evaluator, metric and integration sees it. It is the one place in evalr that reads field types:

```python
from evalr import verdict_fields

for field in verdict_fields(Helpfulness):
    print(field.name, field.kind.value, field.lower, field.upper, field.optional)
```

```text
rating ordinal 1.0 5.0 False
resolved binary None None False
topic categorical None None False
tone categorical None None True
share_done numeric 0.0 1.0 False
reason text None None True
```

Each `VerdictField` also has the field's `description`, its `choices` (a `Literal`'s values or an `Enum`'s members, and `(False, True)` for a binary field) and whether the model `required` it.

## Verdicts

An evaluator returns a `Verdict[V]`, an immutable Pydantic model that wraps the value with what it takes to trust it and trace it:

| Field | Holds |
|---|---|
| `value` | The verdict type's instance |
| `confidence` | The probability that each field's value is right, from 0 to 1, for the fields the evaluator has one for. Decision models report them; most language-model judges do not. Its keys must be fields of the verdict type. |
| `evaluator`, `version` | Who judged, and which version of it |
| `latency` | Wall-clock seconds the evaluation took |
| `cost` | US dollars, when the evaluator knows |
| `trace_id` | The OpenTelemetry trace the evaluation ran in, as 32 hex digits, when there was one |

```python
from evalr import Verdict

verdict = Verdict(
    value=Helpfulness(rating=4, resolved=True, reason="It refunded the charge"),
    confidence={"resolved": 0.92},
    evaluator="helpfulness-decision",
    version="3f2a9c0d1e4b",
)
print(verdict.value.rating, verdict.confidence["resolved"])
```

You rarely build one by hand: evaluators do, through [`judging`](function-evaluators.md#your-own-evaluators), which fills in the latency and the trace.

### Versions keep verdicts apart

Every evaluator has a name and a version, and every verdict records both. When an evaluator changes (its instructions are retrained, its thresholds recalibrated, its function rewritten), its version changes, so verdicts from before and after are never mixed in a metric, a score or an experiment. Trained evaluators derive their version from what they are: a DSPy judge hashes its program and types, and a decision evaluator its model, types, instructions and thresholds. A function evaluator's version is given, so bump it when the function changes.

## Designing a verdict type

- **Describe every field.** The description is the only instruction a judge has for the field, and the text of a decision model's question.
- **Prefer bounded ratings** (`Annotated[int, Field(ge=1, le=5)]`) to open-ended numbers. They are ordinal, their agreement is measured over the scale, and a decision model can answer them as a choice.
- **Give text fields a default.** A decision model cannot write text, so it can only judge a type whose text fields can be left empty. `reason: str | None = None` works with every kind of evaluator; a required `str` limits the type to language-model judges.
- **Keep it flat.** One level of fields of the kinds above. A verdict that needs structure is usually two verdict types.
- **Avoid clashes with the input type.** A DSPy judge's signature has a field for every field of the input and of the verdict, so their names must differ, and `reasoning` is DSPy's.

## Feedback types from artifactr and reflexr

artifactr's and reflexr's feedback types are Pydantic models, so they are verdict types as they are: an evaluator can give the same `Helpfulness` feedback people give in a thread. Both libraries register a feedback type under a name (`helpfulness`), and scores are named `{type}.{field}` after it, the convention the three libraries share. evalr names scores after the class, in snake case, unless told otherwise: pass the registered name as `type_name` where it differs ([Scores and score sinks](scores.md#names-and-ids)).
