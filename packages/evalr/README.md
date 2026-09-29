<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/banner-dark.svg">
  <img alt="evalr: judges that give typed verdicts, trained on people's feedback and measured against it." src="docs/assets/brand/banner-light.svg" width="100%">
</picture>

<p>
  <a href="https://github.com/alexnodeland/evalr/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/alexnodeland/evalr/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <img alt="Python 3.12, 3.13 and 3.14" src="https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-00704F">
  <img alt="Coverage: 100%" src="https://img.shields.io/badge/coverage-100%25-00704F">
  <img alt="Typed: pyright strict" src="https://img.shields.io/badge/typed-pyright%20strict-00704F">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-00704F"></a>
</p>

**evalr** is a Python library for typed evaluation of agent systems. An evaluator judges an input (a chat thread, a workflow run, an artifact version) and returns a verdict: an instance of a Pydantic type, typically one of the feedback types people also give. Because people and evaluators produce the same types, evaluators can be trained on people's feedback and measured against it.

> **Status:** pre-release. v0.1 is built, as planned in [RFC-0001](docs/rfcs/0001-v0.1-implementation-plan.md), and not yet released. The API may still change before 1.0.

## Why

People judge an agent's work in feedback, but only a fraction of it, and only after it has shipped. To know whether a new prompt or model is better before people see it, and how the agent does on the traffic nobody rates, you need evaluators that judge the way people do, and a way to check that they do. evalr's evaluators give the same typed verdicts as people's feedback, so they are trained on it, measured against it field by field, and versioned so that verdicts from different evaluators never mix.

## Install

Python 3.12 or newer. Until evalr is on PyPI, install it from this repository:

```bash
uv add "evalr[all] @ git+https://github.com/alexnodeland/evalr"
```

The core needs only pydantic and the OpenTelemetry API. Extras: `dspy` (DSPy judges and GEPA), `jev` (decision evaluators on TypeSafe's Jev, through pydantic-ai), `langfuse` (datasets, scores and experiments in Langfuse), `hf` (Hugging Face datasets), and `all`.

## Example

People rated support replies. A [DSPy](https://dspy.ai) judge is trained on their verdicts with GEPA, a decision model goes in front of it, and the pair is measured on examples they were not trained on:

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

It needs `OPENAI_API_KEY` (or another provider's, with the models renamed) and `TYPESAFE_API_KEY`. It prints how far the pair agrees with people, then how many threads each evaluator judged, how fast and at what cost.

## What you get

- **Typed verdicts over any Pydantic model.** A field's type decides how it is judged, measured and scored.
- **Two kinds of evaluator, as equals.** DSPy judges with signatures derived from their types, trained with GEPA on people's verdicts and reasons; and decision models such as TypeSafe's Jev, through [pydantic-ai](https://ai.pydantic.dev), with calibrated confidence and thresholds fitted to people. `Fallback` composes them; function evaluators cover what can be computed.
- **Measured against people.** Agreement per field, calibration of confidence, and latency and cost per evaluator version.
- **Datasets that stay put.** Content-hashed, split by a hash of each example's id, and kept at every revision in memory, as JSON Lines files, in [Langfuse](https://langfuse.com) or on the [Hugging Face Hub](https://huggingface.co/datasets).
- **Experiments and online evaluation.** Compare systems on a dataset in memory or in Langfuse; judge live traffic sampled by key, within a budget, with scores in Langfuse or as OpenTelemetry events.
- **End-to-end measures.** Task completion, drop-off and rewrites, defined in terms any application's log can be put in.
- **Built to be tested.** Ports and adapters, in-memory adapters of every port, and contract suites every adapter passes, with 100% branch coverage and pyright strict.

## Documentation

The documentation is built from [`docs/`](docs/index.md); run `make docs-serve` to read it locally at <http://localhost:8000>.

- [Getting started](docs/getting-started.md), [concepts](docs/concepts.md) and the [guides](docs/guides/verdicts.md): verdicts, evaluators, DSPy judges, decision evaluators, calibration, datasets, feedback sources, scores, experiments, metrics, workflow measures, online evaluation and testing.
- [Architecture](docs/architecture.md): concepts, packages and what exists today.
- [Architecture decision records](docs/adr/README.md): why each part is the way it is.
- [RFCs](docs/rfcs/README.md): proposals and the v0.1 build plan.
- [Brand](docs/assets/brand/README.md): the mark, colours and type.

## The family

evalr is part of a family with [artifactr](https://github.com/alexnodeland/artifactr) and [reflexr](https://github.com/alexnodeland/reflexr), which record typed feedback from people and depend on evalr through their `[evals]` extras, and [stackr](https://github.com/alexnodeland/stackr), the infrastructure they run on. evalr imports neither library.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, the trunk-based workflow, and the RFC and ADR process.

## License

[MIT](LICENSE)
