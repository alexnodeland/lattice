# Testing with the contracts

Everything in evalr runs in one process without a network: every port has an in-memory adapter, the language models and decision models have offline stand-ins, and every port has a **contract suite** that checks an adapter keeps the port's promises. evalr's own tests work this way, with 100% branch coverage and no network ([ADR-0005](../adr/0005-quality-gates-and-license.md)); this page shows the patterns for yours.

The examples use [pytest](https://docs.pytest.org) with [pytest-asyncio](https://pytest-asyncio.readthedocs.io) in `asyncio_mode = "auto"`, so async tests need no decorators, and the `Thread` and `Helpfulness` types from [Getting started](../getting-started.md#1-define-the-types).

## In-memory adapters

`evalr.memory` has an adapter of every port that stores or runs something, and behaves like the real ones, as the contract suites check:

| Adapter | Port | Use it for |
|---|---|---|
| `InMemoryDatasetStore` | `DatasetStore` | Code that saves and loads datasets |
| `InMemoryFeedbackSource` | `FeedbackSource` | A fixed list of feedback |
| `InMemoryScoreSink` | `ScoreSink` | Asserting on the scores your code records (`sink.scores`, by id) |
| `InMemoryScoreConfigStore` | `ScoreConfigStore` | Asserting on the score configs your code creates (`store.configs`, by name); creating a name it has raises `ValueError` |
| `InMemoryExperimentTracker` | `ExperimentTracker` | Experiments, kept in `tracker.runs` |
| `BestOf` | `Optimizer` | Choosing between evaluators |

Where your code needs an evaluator but the test is not about judging, a [`FunctionEvaluator`](function-evaluators.md) is an exact, instant stand-in:

```python
from evalr import FunctionEvaluator
from evalr.memory import InMemoryScoreSink
from evalr.online import OnlineEvaluation


def always_helpful(thread: Thread) -> Helpfulness:
    return Helpfulness(rating=5, resolved=True)


async def test_every_turn_is_scored() -> None:
    sink = InMemoryScoreSink()
    online = OnlineEvaluation(
        [FunctionEvaluator(always_helpful, verdict_type=Helpfulness)], sinks=[sink]
    )
    result = await online.judge(Thread(request="Hi", reply="Hello"), key="turn-1")
    assert result.verdicts
    assert {score.name for score in sink.scores.values()} == {
        "helpfulness.rating",
        "helpfulness.resolved",
    }
```

## DSPy judges without a model

DSPy's `DummyLM` answers from a script, in DSPy's own format. Give it each answer as the model would write it:

```python
from dspy.utils import DummyLM

from evalr.dspy import DspyJudge


async def test_the_judge_reads_the_rating() -> None:
    answers = {"rating": "4", "resolved": "True", "reason": "It refunded the charge"}
    judge = DspyJudge(Helpfulness, inputs=Thread, lm=DummyLM([answers]))
    verdict = await judge.evaluate(Thread(request="Charged twice", reply="Refunded."))
    assert verdict.value == Helpfulness(rating=4, resolved=True, reason="It refunded the charge")
```

To test training, give GEPA a scripted reflection model too (`DummyLM([{"new_instruction": "..."}] * 20)`), and a small budget such as `Gepa(reflection_lm=..., max_metric_calls=12)`. evalr's [GEPA tests](https://github.com/alexnodeland/lattice/blob/main/packages/evalr/tests/dspy/scripted.py) script a judge whose answers depend on its instructions, so a test can show training makes it agree with people.

## Decision evaluators without TypeSafe's API

A decision evaluator takes any pydantic-ai model, so a test can give it TypeSafe's own model on a client whose transport answers locally. The SDK's requests, and pydantic-ai's handling of the answers, then run as they do in production:

```python
import json

import httpx2
from pydantic_ai.models.typesafe import TypeSafeModel
from pydantic_ai.providers.typesafe import TypeSafeProvider
from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy

from evalr.decision import DecisionEvaluator


def fake_jev(answers: dict[str, dict[str, object]]) -> TypeSafeModel:
    """Jev, answering each question from a script: {"noul": p} for yes or no, or a choice."""

    def answer(request: httpx2.Request) -> httpx2.Response:
        questions = json.loads(request.content)["questions"]
        return httpx2.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": {name: answers[name] for name in questions},
                "usage": {"input_tokens": 100, "output_tokens": 2},
            },
        )

    client = AsyncTypeSafeClient(
        api_key="test",
        transport=httpx2.MockTransport(answer),
        retry=RetryPolicy(max_retries=0),
    )
    return TypeSafeModel("jev-latest", provider=TypeSafeProvider(typesafe_client=client))


async def test_the_decision_model_is_confident() -> None:
    jev = fake_jev(
        {
            "rating": {
                "type": "choice",
                "choice": "5",
                "confidence": 0.9,
                "probabilities": {"1": 0.02, "2": 0.02, "3": 0.02, "4": 0.04, "5": 0.9},
            },
            "resolved": {"type": "noul", "noul": 0.8},
        }
    )
    decider = DecisionEvaluator(Helpfulness, inputs=Thread, model=jev)
    verdict = await decider.evaluate(Thread(request="Charged twice", reply="Refunded."))
    assert (verdict.value.rating, verdict.value.resolved) == (5, True)
```

evalr's own [fake of Jev](https://github.com/alexnodeland/lattice/blob/main/packages/evalr/tests/decision/jev.py) scripts answers by the text of the input, and fails requests on demand, to test hand-offs and service failures.

## The contract suites

`evalr.contracts` holds one check per port. Each exercises an adapter through its port and raises `ContractViolation`, with a message saying what differed, where it breaks the port's contract. The checks need no test framework: call them from any test.

| Check | Checks that |
|---|---|
| `check_evaluator(evaluator, inputs)` | Each verdict is of the verdict type, names the evaluator and its version, and records the trace it was judged in; the evaluator judges at least one input (it may hand others off); judging does not change its name or version |
| `check_optimizer(optimizer, evaluator, train=, validate=)` | The evaluator given is left alone, and the fitted one gives the same verdict type and passes `check_evaluator` |
| `check_dataset_store(store)` | An unknown name is not found; a saved dataset loads back exactly; saving again changes nothing; a changed dataset makes a new revision and the earlier one still loads; an unknown revision is not found; loading as a type the examples do not satisfy fails validation |
| `check_feedback_source(source)` | Ids are unique, inputs and verdicts are of the source's types, every example has a verdict, and iterating again yields the same examples |
| `check_score_sink(sink, recorded)` | Recording a score again replaces it, every score recorded is kept, and the latest value wins, with its type, trace, span, session, time and metadata; a score without a time may be given the time it was recorded |
| `check_score_config_store(store)` | A new store lists no configs, and every config created is listed by its name |
| `check_experiment_tracker(tracker)` | One item per example, in the dataset's order; a failed task leaves no output and records its error; a failed evaluator records its error while the others still judge; verdicts record the item's trace; names and the dataset's version are kept |

The suites bring their own data where they need it: `ContractInput`, `ContractVerdict` (a verdict type with a field of every kind) and `ContractOutput`.

### Feedback sources

A library or application that implements `FeedbackSource` runs `check_feedback_source` against its own source, over a log or table with some feedback in it. reflexr runs it against `LogFeedbackSource`:

```python
from evalr import Example
from evalr.contracts import check_feedback_source
from evalr.memory import InMemoryFeedbackSource


async def test_the_feedback_source_meets_the_contract() -> None:
    source = InMemoryFeedbackSource(
        [
            Example[Thread, Helpfulness](
                id="fb_1",
                input=Thread(request="Charged twice", reply="Refunded."),
                verdict=Helpfulness(rating=5, resolved=True),
            )
        ],
        input_type=Thread,
        verdict_type=Helpfulness,
    )
    await check_feedback_source(source)
```

### Your own adapters

A new store, sink, tracker or evaluator passes the same suite as evalr's. A score sink has no reads, so `check_score_sink` takes a function that returns what the sink holds, from the sink itself or from a fake of the backend behind it:

```python
from collections.abc import Sequence
from pathlib import Path

from evalr import Score
from evalr.contracts import check_dataset_store, check_evaluator, check_score_sink
from evalr.jsonl import JsonlDatasetStore


class ListSink:
    """A sink of your own: keeps the latest score of each id."""

    def __init__(self) -> None:
        self.kept: dict[str, Score] = {}

    async def record(self, scores: Sequence[Score], /) -> None:
        self.kept.update((score.id, score) for score in scores)


async def test_the_sink_meets_the_contract() -> None:
    sink = ListSink()

    async def recorded() -> list[Score]:
        return list(sink.kept.values())

    await check_score_sink(sink, recorded)


async def test_the_store_meets_the_contract(tmp_path: Path) -> None:
    await check_dataset_store(JsonlDatasetStore(tmp_path))


async def test_the_evaluator_meets_the_contract() -> None:
    evaluator = FunctionEvaluator(always_helpful, verdict_type=Helpfulness)
    await check_evaluator(evaluator, [Thread(request="Hi", reply="Hello")])
```

`check_dataset_store` needs a store that does not yet hold a dataset named `evalr-contract` (pass `name=` to use another), `check_score_sink` a sink that holds no scores yet, and `check_score_config_store` a store that holds no configs yet. evalr's Langfuse sink and config store pass the same two suites against a fake of Langfuse's API.

## Tips

- **Traces.** To assert on spans and trace ids, give evaluators an OpenTelemetry SDK `TracerProvider` with an `InMemorySpanExporter` as `tracer_provider=`, as evalr's own [test fixtures](https://github.com/alexnodeland/lattice/blob/main/packages/evalr/tests/conftest.py) do.
- **Langfuse.** The Langfuse client takes an `httpx_client`, so a test can put a fake of Langfuse's API behind the real client, as evalr's [Langfuse tests](https://github.com/alexnodeland/lattice/blob/main/packages/evalr/tests/langfuse/server.py) do.
- **The Hugging Face Hub.** `HfDatasetStore` and `resolve_revision` take a `HubApi`, a narrow protocol a fake can implement; set `HF_HUB_OFFLINE=1` and `HF_DATASETS_OFFLINE=1` so nothing reaches the Hub. `import_dataset` reads a local directory of data files, at any full commit hash.
- **pydantic-ai's banner.** pydantic-ai may print an observability banner when a decision evaluator's agent is built; `PYDANTIC_AI_NO_BANNER=1` keeps test output clean.
