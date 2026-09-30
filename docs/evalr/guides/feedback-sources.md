# Feedback sources

People's feedback is what evalr's judges learn from and are measured against. It is recorded by the application people use: artifactr and reflexr record typed feedback on threads, turns, runs and chains, and your own application may keep ratings in a table. A **feedback source** turns one type of that feedback into evalr examples, each an input with the verdict a person gave it.

`FeedbackSource` is one of evalr's [ports](../concepts.md#ports-and-adapters): a small protocol that the libraries implement in their `[evals]` extras, so evalr never imports them ([ADR-0006](../adr/0006-ports-and-adapters.md)).

The examples on this page use the `Thread` and `Helpfulness` types from [Getting started](../getting-started.md#1-define-the-types).

## The port

A feedback source has an `input_type`, a `verdict_type` (the feedback type) and an `examples()` method that yields `Example`s asynchronously. It promises three things, which [`check_feedback_source`](testing.md#feedback-sources) checks:

- **Every example has a verdict**: the feedback itself.
- **Ids are stable**, derived from the feedback, so splits and stores treat an example the same way every time it is collected.
- **Iterating again yields the same examples**, until more feedback arrives.

`collect` gathers a source's examples into a [dataset](datasets.md), ready to split, save and train on:

```python
from evalr import Example, collect
from evalr.memory import InMemoryFeedbackSource

source = InMemoryFeedbackSource(
    [
        Example[Thread, Helpfulness](
            id="fb_0192",
            input=Thread(request="I was charged twice", reply="I refunded the duplicate charge."),
            verdict=Helpfulness(rating=5, resolved=True, reason="Fixed at once"),
        ),
        Example[Thread, Helpfulness](
            id="fb_0193",
            input=Thread(request="My order is late", reply="Orders arrive within a week."),
            verdict=Helpfulness(rating=2, resolved=False, reason="It ignored my order"),
        ),
    ],
    input_type=Thread,
    verdict_type=Helpfulness,
)

feedback = await collect("helpfulness", source, description="People's ratings of support replies")
train, validate = feedback.split(0.2)
```

`InMemoryFeedbackSource` yields a fixed list, which suits tests and prototypes.

## reflexr

reflexr's `[evals]` extra ships `reflexr.evals.LogFeedbackSource`, a feedback source over a workspace's log. Each piece of one feedback type becomes an example: the verdict is the feedback, and the input is built by your application from what the feedback is about, since only it knows what its evaluators judge.

Given a reflexr `workspace` in which people give `TriageQuality` feedback (a reflexr `Feedback` type) on the runs of a triage rule:

```python
from pydantic import BaseModel

from evalr import collect
from reflexr.evals import FeedbackContext, LogFeedbackSource


class TriageRun(BaseModel):
    """What a triage judge reads: the service, and what the run did about it."""

    service: str
    emitted: int


def triage_run(context: FeedbackContext[TriageQuality]) -> TriageRun:
    assert context.run is not None  # feedback on a run comes with the run's record
    return TriageRun(
        service=str(context.run.run.scope["service"]), emitted=len(context.run.emitted)
    )


source = LogFeedbackSource(
    workspace,
    feedback_type=TriageQuality,  # the verdict type
    input_type=TriageRun,
    input=triage_run,
    targets={"run"},
)
triage = await collect("triage-quality", source)
```

- **The input builder** receives a `FeedbackContext`: the `feedback_given` envelope (who gave it, and when), the feedback, and what it is about. Feedback on a run or a firing comes with a `RunRecord` of the run, the events that made its rule fire, and the events it emitted; feedback on a causal chain comes with the chain's envelopes. The builder may be async, to read more of the log.
- **Ids are the feedback's event ids**, and an example of feedback on a run carries the trace of the run's latest attempt, so datasets link back to the traces they came from.
- **Metadata** records the tenant, the workspace, the kind of target, who gave the feedback and its position in the log.
- `targets=` limits the source to feedback on some kinds of target (`run`, `firing`, `chain`); every kind by default.

The same extra runs evalr evaluators as rules (`EvaluatorAction`), replays examples against a candidate agent, graph or model as an [experiment](experiments.md) task (`replay_task`), and computes rule-level measures from the log. See [reflexr's architecture](../../reflexr/architecture.md) and its [ADR-0020](../../reflexr/adr/0020-evalr-shared-eval-kit.md).

## artifactr

artifactr records typed feedback from people and evaluators on artifact versions, threads, turns and messages ([artifactr's evaluation guide](../../artifactr/guides/evaluation.md)). Its `[evals]` extra, from [artifactr's RFC-0002](../../artifactr/rfcs/0002-observability-feedback-and-evaluation.md), provides the same pieces: `LogFeedbackSource`, datasets from a workspace's log, with each piece of feedback's target as context; `replay_task`, an experiment task that replays a turn; `OnlineEvaluator`, which judges turns as they end; and the end-to-end measures, `TaskCompletion`, `thread_sessions` and `artifact_histories`. See [Evaluating with evalr](../../artifactr/guides/evaluation.md#evaluating-with-evalr) in artifactr's guide.

## A source of your own

Anything that yields examples with verdicts is a feedback source. Here, ratings an application keeps in its own database:

```python
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class Rating:
    """A row of the application's ratings table."""

    id: int
    request: str
    reply: str
    stars: int
    solved: bool
    comment: str | None


class RatingsSource:
    """People's ratings of replies, as examples."""

    input_type = Thread
    verdict_type = Helpfulness

    def __init__(self, rows: list[Rating]) -> None:
        self.rows = rows  # in an application, a query

    async def examples(self) -> AsyncIterator[Example[Thread, Helpfulness]]:
        for row in self.rows:
            yield Example[Thread, Helpfulness](
                id=f"rating-{row.id}",  # stable: derived from the rating
                input=Thread(request=row.request, reply=row.reply),
                verdict=Helpfulness(rating=row.stars, resolved=row.solved, reason=row.comment),
            )


ratings = RatingsSource([Rating(7, "Cancel my plan", "Done.", 4, True, None)])
from_ratings = await collect("ratings", ratings)
```

Before relying on a source, check it against the port's contract with `check_feedback_source`, as reflexr does for `LogFeedbackSource` ([Testing with the contracts](testing.md#feedback-sources)).
