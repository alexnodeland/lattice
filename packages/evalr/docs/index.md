---
title: evalr
description: A Python library for typed evaluation of agent systems, with judges trained on people's feedback and measured against it.
hide:
  - navigation
---

<div class="evalr-hero" markdown>

<h1 class="evalr-visually-hidden">evalr</h1>

![evalr](assets/brand/lockup-light.svg#gh-light-mode-only)
![evalr](assets/brand/lockup-dark.svg#gh-dark-mode-only)

A Python library for typed evaluation of agent systems: judges that give typed verdicts, trained on people's feedback and measured against it.

</div>

!!! note "Pre-release"

    evalr v0.1 is built, as planned in [RFC-0001](rfcs/0001-v0.1-implementation-plan.md), and not yet released: install it from GitHub. The API may still change before 1.0.

## Why: judges you can check

An agent's quality is decided by the people it serves. They say so in feedback: this reply helped, that plan missed the point, this draft needed rewriting. But people judge a fraction of the work, and only after it has shipped. To know whether a new prompt or model is better before people see it, and how the agent is doing on the traffic nobody rates, you need evaluators that judge the way people do.

evalr makes that checkable. An evaluator's verdict is an instance of the same type people use to give feedback, so:

- **Evaluators are trained on people's feedback.** A language-model judge learns from people's verdicts and the reasons they gave; a decision model's thresholds are fitted to them.
- **Evaluators are measured against people.** Agreement is computed field by field, with the measures that suit each field, and confidence is checked against how often it is right.
- **Every verdict says who gave it.** Evaluators are versioned, so verdicts from a retrained judge never mix with its predecessor's.
- **Cheap where it can be, thorough where it must be.** A decision model answers in milliseconds, and hands what it is unsure of to a language-model judge.

## A short example

People rated support replies. A DSPy judge is trained on their verdicts with GEPA, a decision model goes in front of it, and the pair is measured on examples they were not trained on:

```python
import asyncio
from typing import Annotated

import dspy
from pydantic import BaseModel, Field

from evalr import Fallback, measure, optimize
from evalr.decision import DecisionEvaluator
from evalr.dspy import DspyJudge, Gepa
from evalr.jsonl import JsonlDatasetStore


class Thread(BaseModel):
    request: str = Field(description="What the person asked for")
    reply: str = Field(description="The agent's reply")


class Helpfulness(BaseModel):  # the feedback people give, and the evaluators' verdict
    """Whether the reply helped the person."""

    rating: Annotated[int, Field(ge=1, le=5, description="How much the reply helped")]
    resolved: bool = Field(description="The request was fully addressed")
    reason: str | None = Field(default=None, description="Why, in a sentence")


async def main() -> None:
    feedback = await JsonlDatasetStore("datasets").load(  # threads with people's verdicts
        "helpfulness", input_type=Thread, verdict_type=Helpfulness
    )
    train, validate = feedback.split(0.2)

    judge = DspyJudge(Helpfulness, inputs=Thread, lm=dspy.LM("openai/gpt-5-mini"))
    trained = await optimize(  # GEPA learns from people's verdicts, and their reasons
        judge,
        train=train,
        validate=validate,
        optimizer=Gepa(reflection_lm=dspy.LM("openai/gpt-5")),
    )

    decider = DecisionEvaluator(Helpfulness, inputs=Thread, min_confidence=0.7)  # Jev
    evaluator = Fallback(decider, trained)  # the judge answers only where Jev is unsure

    measurement = await measure(evaluator, validate)
    print(measurement.agreement.score)  # agreement with people, from 0 to 1
    for stats in measurement.stats:
        print(stats.evaluator, stats.n, stats.p95_latency, stats.total_cost)


asyncio.run(main())
```

It prints how far the pair agrees with people, then how many threads each evaluator judged, how fast and at what cost. [Getting started](getting-started.md) builds the same thing step by step, from the dataset up.

## What you get

- **Typed verdicts over any Pydantic model.** A field's type decides how it is judged, measured and scored, so an application's feedback types work as they are. [Typed verdicts and field kinds](guides/verdicts.md)
- **Two kinds of evaluator, as equals.** [DSPy judges](guides/dspy-judges.md) with signatures derived from their types, trained with GEPA, and [decision models](guides/decision-evaluators.md) such as TypeSafe's Jev, with calibrated confidence and [thresholds fitted to people](guides/calibration.md). `Fallback` composes them, and [function evaluators](guides/function-evaluators.md) cover what can be computed.
- **Measured against people.** Agreement per field (accuracy and Cohen's kappa, mean absolute error and rank correlation), calibration of confidence, and latency and cost per evaluator version. [Agreement and calibration metrics](guides/metrics.md)
- **Datasets that stay put.** Examples keep their ids for life, datasets are versioned by their content and split by a hash of each id, and stores keep every revision: in memory, as JSON Lines files, in Langfuse, or on the Hugging Face Hub. [Datasets, splits and stores](guides/datasets.md)
- **Feedback in, scores out.** [Feedback sources](guides/feedback-sources.md) turn people's feedback into examples, and every verdict becomes [scores](guides/scores.md) named like people's feedback, beside the traces they judge.
- **Experiments and online evaluation.** Compare systems on a dataset, [in memory or in Langfuse](guides/experiments.md), and judge [live traffic](guides/online.md) sampled by key, within a budget, with results as Langfuse scores or OpenTelemetry events.
- **End-to-end measures.** Task completion, drop-off and rewrites, defined in terms any application's log can be put in. [Workflow measures](guides/measures.md)
- **Built to be tested.** A pure core, ports with in-memory adapters, and contract suites that every adapter passes, yours included. evalr itself is held to 100% branch coverage and pyright strict. [Testing with the contracts](guides/testing.md)

## Where to go next

| If you want to | Read |
|---|---|
| Build something now | [Getting started](getting-started.md) |
| Understand the ideas | [Concepts](concepts.md) |
| Understand one part in depth | The [guides](guides/verdicts.md) |
| Look up a class or function | The [API reference](reference/index.md) |
| Understand why it is built this way | The [architecture](architecture.md) and the [decision records](adr/README.md) |
| Contribute | [Contributing](project/contributing.md) |
