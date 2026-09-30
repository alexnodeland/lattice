# Decision evaluators

A decision model answers typed questions (yes or no, one of several choices, a score) in tens to hundreds of milliseconds, with a probability for each answer, and writes no free text. TypeSafe's **Jev** is one, and pydantic-ai supports decision models natively. `DecisionEvaluator` makes one an evaluator: fast and cheap enough to judge live traffic, with confidence that means what it says, handing what it is unsure of to a language-model judge ([ADR-0002](../adr/0002-dspy-judges-and-decision-models-as-equals.md), [ADR-0008](../adr/0008-decision-only-views-and-hand-off-by-composition.md)).

It needs the `jev` extra, and TypeSafe's API key (`TYPESAFE_API_KEY`) when it first runs. The examples on this page use the `Thread` and `Helpfulness` types from [Getting started](../getting-started.md#1-define-the-types).

## A decision evaluator

```python
from evalr.decision import DecisionEvaluator

decider = DecisionEvaluator(Helpfulness, inputs=Thread)

verdict = await decider.evaluate(
    Thread(request="I was charged twice", reply="I refunded the duplicate charge.")
)
print(verdict.value, verdict.confidence)
```

It prints the verdict and how sure the model is of each field, such as:

```text
rating=5 resolved=True reason=None {'rating': 0.9, 'resolved': 0.92}
```

It is a pydantic-ai `Agent` on a decision model, `typesafe:jev-latest` by default, whose output type is the verdict type's decision-only view. The evaluator is named `{verdict type}-decision` (`helpfulness-decision`) unless you pass `name=`. Credentials are needed only when it first runs, so evaluators can be built at import time.

- `model=` takes any pydantic-ai decision model, or its name. **Pin a version** (`"typesafe:jev-1.13.0"`) once you have [calibrated](calibration.md) an evaluator: `jev-latest` can change under a fixed evaluator version.
- `instructions=` is background the model reads with every question.
- `reason` was left empty: a decision model writes no text. [Hand-off and fallback](#hand-off-and-fallback) fills it.

## The decision-only view

pydantic-ai asks a decision model one question per field of its output type, and a decision model accepts only some field types. So the evaluator's output type is a view of the verdict type, derived by `decision_view`, with only the fields a decision model can fill:

| Verdict field | In the view |
|---|---|
| `bool`, required | A yes-or-no question |
| `Literal` or `Enum` of 2 to 255 strings or whole numbers | A choice, unchanged |
| `int` bounded on both sides, with 2 to 255 values (an ordinal rating) | A choice of every value on the scale |
| `float` from 0 to an upper bound, required | A yes-or-no question, scaled to the bound |
| Anything else: text, unbounded numbers, an optional `bool` or `float` | Left out |

Each question's text is the field's description, and the verdict type's docstring is the decision's goal.

```python
from evalr.decision import decision_view

view = decision_view(Helpfulness)
print(view.decided, view.left_out)
```

```text
('rating', 'resolved') ('reason',)
```

A field left out keeps its default in the verdict. So a required field that the view would leave out (a required `str`, say) is refused when the evaluator is built, with `UnsupportedField`: give it a default, or judge the type with a language model. This is why [verdict types](verdicts.md#designing-a-verdict-type) give their text fields a default.

## Confidence and thresholds

A verdict's confidence is the probability that each field's value is right: for a choice, the model's probability of the choice; for a yes-or-no field, the probability of the answer given. pydantic-ai reports a yes-or-no field's confidence relative to the threshold, and evalr recovers the model's probability from it, so confidence means the same for every field and every kind of evaluator, and [calibration metrics](metrics.md#calibration) apply to all of them.

`decide(input)` asks the model without handing off, and returns everything it answered, including each yes-or-no field's raw probability of yes:

```python
decision = await decider.decide(
    Thread(request="I was charged twice", reply="I refunded the duplicate charge.")
)
print(decision.probabilities, decision.model, decision.cost)
```

It prints the probability of yes for `resolved`, the model that answered, and the cost in US dollars, such as:

```text
{'resolved': 0.92} jev-1.13.0 4.2e-05
```

Two thresholds decide what the evaluator does with those probabilities:

| Threshold | Default | Effect |
|---|---|---|
| `boolean_threshold` | 0.5 | A yes-or-no field is yes when its probability of yes is at or above it (pydantic-ai's `decision_boolean_threshold`) |
| `min_confidence` | none | The evaluator hands off when any field's confidence is below it |

Both are what [calibration](calibration.md) fits to people's verdicts. The evaluator's version is a hash of the model's name, the types, the instructions and both thresholds, so a recalibrated evaluator is a new version.

## The state it reads

A decision model reads its input as one text, its state. By default the evaluator renders the input with an `InputFormatter` within 30,000 estimated tokens, under Jev's 32K limit: each field is a section headed by its name and description, long lists lose their oldest items first, and long texts are shortened in the middle ([What a judge reads](dspy-judges.md#what-a-judge-reads)). `formatter=` takes any callable from the input to text, such as one that summarizes a long thread:

```python
def last_exchange(thread: Thread) -> str:
    return f"Request: {thread.request}\nReply: {thread.reply}"


decider = DecisionEvaluator(Helpfulness, inputs=Thread, formatter=last_exchange)
```

## Hand-off and fallback

A decision evaluator declines what it cannot judge well by raising `HandOff`:

- when pydantic-ai hands off (`DecisionHandOff`: the model routes the step elsewhere, or asks for a tool)
- when any field's confidence is below `min_confidence`

Service failures, such as an unreachable API, are not hand-offs: they raise as they are. The evaluation's span records a hand-off and its reason as attributes (`evalr.handed_off`, `evalr.hand_off.reason`), not as an error.

`Fallback`, from the core, composes two evaluators of one verdict type: the primary judges, and whatever it hands off goes to the fallback. A decision model backed by a DSPy judge is the usual pairing. The judge fills the whole verdict, text included, and only runs where the decision model is unsure:

```python
import dspy

from evalr import Fallback
from evalr.dspy import DspyJudge

decider = DecisionEvaluator(Helpfulness, inputs=Thread, min_confidence=0.7)
judge = DspyJudge(Helpfulness, inputs=Thread, lm=dspy.LM("openai/gpt-5-mini"))
evaluator = Fallback(decider, judge)

for reply in ("I refunded the duplicate charge.", "Have you tried turning it off and on?"):
    verdict = await evaluator.evaluate(Thread(request="I was charged twice", reply=reply))
    print(verdict.evaluator, verdict.value.rating, verdict.value.reason)
```

Where Jev is confident, its verdict stands; where it is not, the judge's does. For example:

```text
helpfulness-decision 5 None
helpfulness-judge 2 It did not help
```

- **Each verdict names the evaluator that actually gave it**, so the two are measured apart: in a [measurement](metrics.md#measuring-an-evaluator), `stats` has one entry per evaluator version, with its own latency and cost.
- **`Fallback(..., min_confidence=)`** hands off low-confidence verdicts itself, for a primary that reports confidence but does not hand off on its own. Setting the threshold on the decision evaluator instead lets [calibration](calibration.md) tune it.
- **The two evaluators must give the same verdict type**; otherwise `Fallback` raises `TypeError`.
- The composition runs in a span named `evalr.fallback {name}`, with `evalr.fallback.handed_off` and `evalr.fallback.reason`. Its name is `{primary}+{fallback}`, and its version a hash of both evaluators' names and versions and its threshold.

Neither evaluator knows about the other: `Fallback` composes any two evaluators, so the fallback could as well be a second decision model, or the primary a [function evaluator](function-evaluators.md#your-own-evaluators) that hands off what its rules do not cover.

## Cost and traces

A decision verdict's `cost` is pydantic-ai's, from the model's price, and its `latency` is measured around the request. The model that actually answered (`jev-1.13.0` for `jev-latest`) is recorded on the evaluation span as `gen_ai.response.model`. pydantic-ai traces the agent's run itself, under the evaluation span, once the application turns on pydantic-ai's instrumentation.
