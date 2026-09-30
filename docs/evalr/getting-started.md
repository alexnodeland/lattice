# Getting started

This page builds an evaluator for a support agent's replies, the way you would for a real application: define what people judge, gather their verdicts into a dataset, measure a simple baseline, train a language-model judge on people's feedback, put a fast decision model in front of it, and record what it judges as scores. Along the way it covers the pieces every use of evalr has: a verdict type, a dataset, evaluators, `measure`, an optimizer, and a score sink.

## Install

evalr needs Python 3.12 or newer. Until it is published to PyPI, install it from its directory in [lattice](https://github.com/alexnodeland/lattice), the family's repository:

=== "uv"

    ```bash
    uv add "evalr[all] @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/evalr"
    ```

=== "pip"

    ```bash
    pip install "evalr[all] @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/evalr"
    ```

The core install covers verdicts, function evaluators, datasets, metrics, in-memory adapters, JSON Lines files, workflow measures and online evaluation, with pydantic and the OpenTelemetry API as its only dependencies. The integrations are extras:

| Extra | Adds | Needs |
|---|---|---|
| `dspy` | [DSPy judges](guides/dspy-judges.md) and GEPA | A language model: DSPy names models as LiteLLM does (`openai/gpt-5-mini`), with the provider's key in the environment (`OPENAI_API_KEY`) |
| `jev` | [Decision evaluators](guides/decision-evaluators.md) and [calibration](guides/calibration.md), through pydantic-ai | TypeSafe's API key, `TYPESAFE_API_KEY` |
| `langfuse` | Langfuse [datasets](guides/datasets.md#langfuse-datasets), [scores](guides/scores.md#scores-in-langfuse) and [experiments](guides/experiments.md#experiments-in-langfuse) | A Langfuse project |
| `hf` | [Hugging Face datasets](guides/datasets.md#the-hugging-face-hub) | A Hugging Face token, for private or published datasets |
| `all` | Every extra | |

Combine extras with commas, as in `evalr[dspy,jev]`.

The steps below build one script. Code that awaits runs inside `async def main()`, as in [the complete script](#the-complete-script) at the end.

## 1. Define the types

An evaluator reads an **input** and gives a **verdict**, and both are Pydantic models. The verdict type is what people judge: here, whether a reply helped.

```python
from typing import Annotated

from pydantic import BaseModel, Field


class Thread(BaseModel):
    """A person's request and the agent's reply."""

    request: str = Field(description="What the person asked for")
    reply: str = Field(description="The agent's reply")


class Helpfulness(BaseModel):
    """Whether the reply helped the person."""

    rating: Annotated[int, Field(ge=1, le=5, description="How much the reply helped")]
    resolved: bool = Field(description="The request was fully addressed")
    reason: str | None = Field(default=None, description="Why, in a sentence")
```

Each field's type decides how it is judged and measured: `rating` is an ordinal scale, `resolved` a yes or no, and `reason` free text, which only language-model judges write and which agreement with people does not compare. Each description is the instruction evaluators read for the field. [Typed verdicts and field kinds](guides/verdicts.md) covers the rest.

## 2. Gather people's verdicts

A dataset holds inputs with the verdicts people gave them. In an application they come from people's feedback, through a [feedback source](guides/feedback-sources.md); here they are written out:

```python
from evalr import Dataset, Example

rated = [
    ("fb_01", "I was charged twice", "I refunded the duplicate charge.", 5, True, "Fixed at once"),
    ("fb_02", "My parcel hasn't arrived", "Parcels arrive within a week.", 2, False, "Ignored me"),
    ("fb_03", "How do I change my email?", "Go to Settings, then Account.", 5, True, "Clear"),
    ("fb_04", "The app crashes on start", "Have you tried reinstalling?", 2, False, "Generic"),
    ("fb_05", "Cancel my subscription", "Done: it ends on 30 September.", 5, True, "Done"),
    ("fb_06", "Can I get March's invoice?", "Invoices are in your account.", 3, False, "Not sent"),
    ("fb_07", "Charged after cancelling", "I refunded the charge.", 5, True, "Refunded"),
    ("fb_08", "My discount code fails", "Codes can't be combined.", 3, False, "No fix"),
    ("fb_09", "Wrong size delivered", "I emailed you a return label.", 4, True, "Helpful"),
    ("fb_10", "Where is my refund?", "Refunds take 3 to 5 days.", 2, False, "Didn't check"),
]

dataset = Dataset(
    "helpfulness",
    [
        Example[Thread, Helpfulness](
            id=feedback_id,
            input=Thread(request=request, reply=reply),
            verdict=Helpfulness(rating=rating, resolved=resolved, reason=reason),
        )
        for feedback_id, request, reply, rating, resolved, reason in rated
    ],
    input_type=Thread,
    verdict_type=Helpfulness,
    description="People's ratings of support replies",
)
train, validate = dataset.split(0.3)
```

`split` sends each example to training or validation by a hash of its id, so an example never moves between the two as the dataset grows. Ten examples are enough to run this page, not to train a judge you can trust: collect at least a few dozen, and [save them](guides/datasets.md#stores) to a store that keeps every revision.

## 3. Measure a baseline

Before training anything, measure something simple. A [function evaluator](guides/function-evaluators.md) is a function of the input, and `measure` compares its verdicts with people's:

```python
from evalr import FunctionEvaluator, measure


def says_it_acted(thread: Thread) -> Helpfulness:
    """A baseline: a reply that says it did something helped."""
    reply = thread.reply.lower()
    acted = any(word in reply for word in ("refunded", "done", "emailed", "go to"))
    return Helpfulness(rating=5 if acted else 2, resolved=acted)


baseline = FunctionEvaluator(says_it_acted, verdict_type=Helpfulness)
measurement = await measure(baseline, validate)
print(measurement.agreement.score, measurement.agreement.fields["resolved"].accuracy)
```

`measurement.agreement` is how far the evaluator agrees with people, from 0 to 1, overall and field by field, with the measures that suit each field: accuracy and Cohen's kappa for `resolved`, mean absolute error and rank correlation for `rating`. [Agreement and calibration metrics](guides/metrics.md)

## 4. Train a judge on people's feedback

A DSPy judge is a language-model evaluator whose prompt is derived from the two types. GEPA trains its instructions on the training examples, learning from the reasons people gave, and keeps a change only if it agrees better with people on the validation examples:

```python
import dspy

from evalr import optimize
from evalr.dspy import DspyJudge, Gepa

judge = DspyJudge(Helpfulness, inputs=Thread, lm=dspy.LM("openai/gpt-5-mini"))
trained = await optimize(
    judge,
    train=train,
    validate=validate,
    optimizer=Gepa(reflection_lm=dspy.LM("openai/gpt-5")),
)
trained.save("helpfulness-judge.json")
```

The trained judge has a new version, a hash of its program, and every verdict it gives records it, so its scores never mix with the untrained judge's. The JSON file holds its program and how it was trained; keep it in your repository and load it with `DspyJudge.load`. [DSPy judges and GEPA](guides/dspy-judges.md)

## 5. Put a decision model in front

A decision model such as TypeSafe's Jev answers the verdict's yes-or-no and choice questions in milliseconds, with a probability for each, but writes no text. `Fallback` puts it in front of the judge: where Jev is less than 70% sure of a field, it hands the thread to the judge, which fills in the whole verdict, reason included.

```python
from evalr import Fallback
from evalr.decision import DecisionEvaluator

decider = DecisionEvaluator(Helpfulness, inputs=Thread, min_confidence=0.7)
evaluator = Fallback(decider, trained)

measurement = await measure(evaluator, validate)
for stats in measurement.stats:
    print(stats.evaluator, stats.n, stats.mean_latency, stats.total_cost)
```

Each verdict names the evaluator that actually gave it, so `stats` shows how many threads each judged, and what they cost. [Calibration](guides/calibration.md) tunes the 70% on your data.

## 6. Record what it judges

An evaluator's verdicts become scores, one per field, named `{type}.{field}` as people's feedback is, so they sit side by side:

```python
from evalr import scores
from evalr.memory import InMemoryScoreSink

sink = InMemoryScoreSink()
verdict = await evaluator.evaluate(
    Thread(request="My order is late", reply="I've sent a replacement by express post.")
)
await sink.record(scores(verdict, subject="turn_01"))

for score in sink.scores.values():
    print(score.name, score.value, score.evaluator)
```

`InMemoryScoreSink` suits a first run and tests. `LangfuseScoreSink` records the same scores in Langfuse, on the traces they judge, and [online evaluation](guides/online.md) judges a sample of live traffic this way, within a budget. [Scores and score sinks](guides/scores.md)

## The complete script

??? example "The complete script"

    ```python title="evaluate.py"
    import asyncio
    from typing import Annotated

    import dspy
    from pydantic import BaseModel, Field

    from evalr import Dataset, Example, Fallback, FunctionEvaluator, measure, optimize, scores
    from evalr.decision import DecisionEvaluator
    from evalr.dspy import DspyJudge, Gepa
    from evalr.memory import InMemoryScoreSink


    class Thread(BaseModel):
        """A person's request and the agent's reply."""

        request: str = Field(description="What the person asked for")
        reply: str = Field(description="The agent's reply")


    class Helpfulness(BaseModel):
        """Whether the reply helped the person."""

        rating: Annotated[int, Field(ge=1, le=5, description="How much the reply helped")]
        resolved: bool = Field(description="The request was fully addressed")
        reason: str | None = Field(default=None, description="Why, in a sentence")


    rated = [
        ("fb_01", "I was charged twice", "I refunded the duplicate charge.", 5, True, "Fixed at once"),
        ("fb_02", "My parcel hasn't arrived", "Parcels arrive within a week.", 2, False, "Ignored me"),
        ("fb_03", "How do I change my email?", "Go to Settings, then Account.", 5, True, "Clear"),
        ("fb_04", "The app crashes on start", "Have you tried reinstalling?", 2, False, "Generic"),
        ("fb_05", "Cancel my subscription", "Done: it ends on 30 September.", 5, True, "Done"),
        ("fb_06", "Can I get March's invoice?", "Invoices are in your account.", 3, False, "Not sent"),
        ("fb_07", "Charged after cancelling", "I refunded the charge.", 5, True, "Refunded"),
        ("fb_08", "My discount code fails", "Codes can't be combined.", 3, False, "No fix"),
        ("fb_09", "Wrong size delivered", "I emailed you a return label.", 4, True, "Helpful"),
        ("fb_10", "Where is my refund?", "Refunds take 3 to 5 days.", 2, False, "Didn't check"),
    ]

    dataset = Dataset(
        "helpfulness",
        [
            Example[Thread, Helpfulness](
                id=feedback_id,
                input=Thread(request=request, reply=reply),
                verdict=Helpfulness(rating=rating, resolved=resolved, reason=reason),
            )
            for feedback_id, request, reply, rating, resolved, reason in rated
        ],
        input_type=Thread,
        verdict_type=Helpfulness,
        description="People's ratings of support replies",
    )


    def says_it_acted(thread: Thread) -> Helpfulness:
        """A baseline: a reply that says it did something helped."""
        reply = thread.reply.lower()
        acted = any(word in reply for word in ("refunded", "done", "emailed", "go to"))
        return Helpfulness(rating=5 if acted else 2, resolved=acted)


    async def main() -> None:
        train, validate = dataset.split(0.3)

        baseline = FunctionEvaluator(says_it_acted, verdict_type=Helpfulness)
        measurement = await measure(baseline, validate)
        print("baseline", measurement.agreement.score)

        judge = DspyJudge(Helpfulness, inputs=Thread, lm=dspy.LM("openai/gpt-5-mini"))
        trained = await optimize(
            judge,
            train=train,
            validate=validate,
            optimizer=Gepa(reflection_lm=dspy.LM("openai/gpt-5")),
        )
        trained.save("helpfulness-judge.json")

        decider = DecisionEvaluator(Helpfulness, inputs=Thread, min_confidence=0.7)
        evaluator = Fallback(decider, trained)
        measurement = await measure(evaluator, validate)
        print("evaluator", measurement.agreement.score)
        for stats in measurement.stats:
            print(stats.evaluator, stats.n, stats.mean_latency, stats.total_cost)

        sink = InMemoryScoreSink()
        verdict = await evaluator.evaluate(
            Thread(request="My order is late", reply="I've sent a replacement by express post.")
        )
        await sink.record(scores(verdict, subject="turn_01"))
        for score in sink.scores.values():
            print(score.name, score.value, score.evaluator)


    asyncio.run(main())
    ```

It needs `OPENAI_API_KEY` (or another provider's key, with the models renamed) and `TYPESAFE_API_KEY`.

## Next steps

- Read the [concepts](concepts.md), then the guide for each part you use.
- Gather verdicts from people's feedback with a [feedback source](guides/feedback-sources.md), and keep datasets in [Langfuse or on the Hugging Face Hub](guides/datasets.md#stores).
- Compare a new prompt or model against the current one in an [experiment](guides/experiments.md).
- Judge live traffic with [online evaluation](guides/online.md).
- Test your evaluation code without a network, with [the in-memory adapters and contract suites](guides/testing.md).
