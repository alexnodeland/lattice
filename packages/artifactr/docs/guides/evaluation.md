# Evaluation

To improve an agent you need to know where it helps and where it fails. artifactr records judgements of its work as **typed feedback**: people's ratings and corrections, and evaluators' verdicts, on artifact versions, threads, turns and messages ([ADR-0028](../adr/0028-typed-feedback-as-events.md)). Feedback lives in the workspace's log beside what it judges, so datasets can be rebuilt from any log, and it links to the traces of the work it is about.

## Feedback types

A feedback type is a Pydantic model that subclasses `Feedback`. It is registered by name, like an artifact type, and declares the targets it can be given on:

```python
from typing import Annotated, Literal

from pydantic import Field

from artifactr import Feedback


class Helpfulness(Feedback, name="helpfulness", targets={"turn", "thread"}):
    rating: Annotated[int, Field(ge=1, le=5)]
    reason: str | None = None


class DraftQuality(Feedback, targets={"artifact"}):  # registered as "draft_quality"
    usable: bool
    problem: Literal["wrong", "incomplete", "style"] | None = None
```

Choose field types for how they will be scored: bounded numbers are numeric scores, `bool` is yes or no, `Literal` and `Enum` are categories, and `str` is free text. Intermediate base classes pass `abstract=True`.

## Targets

| Target | Use it for |
|---|---|
| `ArtifactTarget(artifact_id, version)` | One version of an artifact, such as the draft the agent wrote |
| `ThreadTarget(thread_id)` | A whole thread: was the task done? |
| `TurnTarget(run_id)` | The agent's turn: its run, across any pauses |
| `MessageTarget(message_id, thread_id, run_id=None)` | One message. For the agent's messages, pass the `run_id` of its `message_posted`, which links the feedback to the run's trace |

## Giving feedback

Feedback is a command, `GiveFeedback`, so it goes through the same write path as every other change ([ADR-0037](../adr/0037-feedback-targets-and-evaluators.md)):

```python
from artifactr.core import GiveFeedback, TurnTarget

await ws.commit(
    GiveFeedback(
        feedback_type="helpfulness",
        target=TurnTarget(run_id=run_id),
        value={"rating": 2, "reason": "It ignored my edits."},
    )
)
```

Core checks that the type is registered and declares the target's kind, that the value validates against the type, and that the target exists, then records a `feedback_given` event with the validated value. The person or evaluator who gave it is the envelope's actor. Feedback on a thread, turn or message belongs to that thread; feedback on an artifact version is workspace-scoped.

Every surface has it: a `give_feedback` command frame over WebSocket or REST ([protocol](../protocol.md#client-frames-commands)), and a `give_feedback` tool over MCP.

## Evaluators

An evaluator's verdict is feedback of the same types, given by an `EvaluatorActor`:

```python
from artifactr import EvaluatorActor

judge = ws.as_actor(EvaluatorActor(name="helpfulness-judge", version="2026-09-28"))
await judge.commit(
    GiveFeedback(feedback_type="helpfulness", target=TurnTarget(run_id=run_id), value={"rating": 4})
)
```

An evaluator can only give feedback; any other command from one is rejected as `forbidden`. Each version is its own participant, so verdicts from a retrained judge never mix with its predecessor's. Because people and evaluators use the same types, their agreement is a query over the log.

## Reading feedback

Feedback is in the log with everything else:

```python
from artifactr.core import FeedbackGiven

ratings = [
    (envelope.actor, envelope.event.value)
    for envelope in await ws.read()
    if isinstance(envelope.event, FeedbackGiven) and envelope.event.feedback_type == "helpfulness"
]
```

It is also counted in the `artifactr.feedback` metric, by type, target and kind of actor, and each commit is traced ([Observability](observability.md)).

## Scores

Evaluation backends see feedback as scores: one per field, named `{type}.{field}`, typed by the field ([ADR-0038](../adr/0038-feedback-as-scores.md)). `Helpfulness` above becomes `helpfulness.rating`, a numeric score from 1 to 5, and `helpfulness.reason`, a text score. Booleans are 1 or 0, `Literal` and `Enum` fields are categories, and fields left empty are not scored.

`artifactr.scores.FeedbackMirror` follows a workspace's log and sends each piece of feedback's scores to a `ScoreSink`, attached to the trace the feedback is about when there is one, and to the session (the thread) otherwise:

```python
import asyncio

from artifactr.scores import FeedbackMirror

mirror = FeedbackMirror(workspace, sink)
task = asyncio.create_task(mirror.follow())  # until cancelled
```

A turn's feedback lands on the trace of the run's latest attempt, a message's on the trace of the run that posted it, and an artifact version's on the trace it was committed in. Score ids are derived from the feedback's envelope, so a mirror can start over from the beginning of the log without duplicating anything. `sync_score_configs(store)` creates the score configs of every registered feedback type that a `ScoreConfigStore` lacks.

The sink and the store are small protocols, so any backend can implement them:

```python
from artifactr.scores import Score


class PrintingSink:
    async def send(self, score: Score) -> None:
        print(score.name, score.value, score.trace_id or score.session_id)
```

## Scores in Langfuse

With the `langfuse` extra, feedback becomes Langfuse scores beside the traces it judges. `LangfuseScores` is a `ScoreSink`, and `LangfuseScoreConfigs` a `ScoreConfigStore`:

```python
import asyncio

from artifactr.langfuse import LangfuseScoreConfigs, LangfuseScores, langfuse_client
from artifactr.scores import FeedbackMirror, sync_score_configs

langfuse = langfuse_client(tracer_provider=telemetry.tracer_provider)  # or telemetry.langfuse
await sync_score_configs(LangfuseScoreConfigs(langfuse))  # once, at startup
mirror = asyncio.create_task(FeedbackMirror(workspace, LangfuseScores(langfuse)).follow())
```

Score configs give Langfuse each score's type, range and categories, so its UI can offer the same scales for annotation. Langfuse accepts config names of up to 35 characters; a longer `{type}.{field}` raises, and a shorter `name=` on the feedback type fixes it. Scores are queued by the Langfuse client and sent in the background; call `langfuse.flush()` before a short-lived process exits.

## Evaluating with evalr

The `evals` extra connects artifactr to [evalr](https://github.com/alexnodeland/evalr), the eval kit artifactr and reflexr share ([ADR-0029](../adr/0029-evalr-shared-eval-kit.md), [ADR-0044](../adr/0044-the-evalr-adapter.md)). evalr owns the evaluators (DSPy judges optimized with GEPA, TypeSafe Jev decision models, plain functions), datasets, experiments and online evaluation; `artifactr.evals` feeds them from the log and records what they decide back into it:

| You want | Use |
|---|---|
| A dataset of people's feedback, to train or measure a judge | `LogFeedbackSource` |
| To compare a new agent, prompt or model on real turns | `replay_task`, as an experiment's task |
| To judge live turns as they end | `OnlineEvaluator`, in `Runner(evaluators=[...])` |
| Drop-off, the rewrite rate and task completion | `thread_sessions`, `artifact_histories`, `TaskCompletion` |

evalr is not on PyPI yet. artifactr's own development environment pins it by revision; an application installs it from GitHub alongside the extra, for example with `uv add "evalr @ git+https://github.com/alexnodeland/evalr"`.

### Datasets from the log

A `LogFeedbackSource` is evalr's `FeedbackSource` over one workspace's log. Each piece of one feedback type becomes an evalr `Example`, with the feedback as its verdict and an input your code builds from what the feedback is about:

```python
from evalr.core import collect
from pydantic import BaseModel

from artifactr.evals import LogFeedbackSource, TargetContext


class TurnInput(BaseModel):
    said: list[str]
    followed: list[str]


def turn_input(context: TargetContext) -> TurnInput:
    return TurnInput(
        said=[f"{e.actor.kind}: {e.event.content}" for e in context.transcript],
        followed=[a.data.render_for_agent() for a in context.artifacts],
    )


source = LogFeedbackSource(
    workspace, feedback_type=Helpfulness, input_type=TurnInput, input=turn_input
)
dataset = await collect("helpfulness", source)
train, validate = dataset.labelled().split(0.2)
```

The builder gets a `FeedbackContext`: the `feedback_given` envelope and the feedback, and the context of its target. A `FeedbackContext` is a `TargetContext`, so a builder written for target contexts, like `turn_input`, also builds an online evaluator's input. Builders may be async, and may read more of `context.workspace`.

A context is read **as of the end of its target**, so a dataset built weeks later gives a judge the input it would have had as the turn ended:

| Target | Read up to | With |
|---|---|---|
| A turn | The run's last event | The run's events, and its latest trace |
| A message | The message | The run's events up to it, when the target names the run |
| An artifact version | The change that made it | The revision, the version as its type, and the trace it was committed in |
| A thread | The feedback | |

Every context also has the thread's transcript (its `message_posted` envelopes) and the artifacts the thread followed then, at their versions then. Example ids are the envelopes' ids, and examples carry their target's trace id, so datasets link back to traces. Pass `targets={"turn"}` to take one kind of target.

Evaluators' own verdicts are left out unless you pass `include_evaluators=True`: online evaluators record feedback of the same types, and a judge must not be trained on its own verdicts. The source passes evalr's `check_feedback_source` contract.

### Experiments

`replay_task` is an evalr experiment `Task`. For each example, it seeds a fresh in-memory workspace with the thread as it was, sends the message that started the turn to a candidate agent, and hands what the turn did to your output builder. Nothing touches your real workspaces:

```python
from evalr.measures import Turn
from evalr.memory import InMemoryExperimentTracker

from artifactr.evals import Replay, Seed, replay_task


def seed(example: Example[Request, Helpfulness]) -> Seed:
    return Seed(
        prompt=example.input.request,
        messages=[Turn(role="person", text=text) for text in example.input.before],
        artifacts={"doc_1": Doc(text=example.input.doc)},
    )


def reply(replay: Replay) -> Reply:
    return Reply(text=replay.message, edits=len(replay.revisions))


task = replay_task(candidate_agent, app=deps, seed=seed, output=reply, types=[Doc, Plan])
result = await InMemoryExperimentTracker().run_experiment(
    "new-prompt", dataset=dataset, task=task, evaluators=[judge]
)
```

The seed's artifacts keep their ids, and the thread follows them. Its messages are posted and stored as the agent's history, and the agent is not told of the seeding as changes. A `Replay` has the turn's run, its events (tool calls, changes, proposals, messages), the revisions it wrote and its last message. A run that fails fails only its item. evalr's Langfuse tracker runs the same task as a Langfuse experiment.

### Online evaluation

An `OnlineEvaluator` judges a `Runner`'s turns as they end, and records each verdict as feedback:

```python
from evalr.online import Budget

from artifactr.evals import OnlineEvaluator

judging = OnlineEvaluator(
    [helpfulness_judge],  # evalr evaluators whose verdicts are feedback types
    input=turn_input,
    sample_rate=0.1,
    budget=Budget(max_evaluations=1000, max_cost=5.0),
)
runner = Runner(agent, app=deps, evaluators=[judging])
...
await judging.drain()  # at shutdown
```

The `Runner`'s `evaluators` are a port, `TurnEvaluator`: the `Runner` hands each one the turn as it ends, and the evaluation runs in the background, so it never slows the turn, holds the thread, or fails the run. Sampling (by run) and the budget are evalr's `OnlineEvaluation`'s. Each verdict is given with `give_feedback` on the turn by an `EvaluatorActor` with the name and version of the evaluator that gave it, so the `FeedbackMirror` scores it in Langfuse like people's feedback, and the two can be compared. A failure (of the input builder, an evaluator, or a verdict the target does not accept) is logged on the `artifactr.evals` logger and recorded on the evaluation's result; an evaluator that hands off records nothing. The evaluation's spans, and the feedback's commit, are in the turn's trace.

Pass `outcomes={"completed", "paused"}` to judge paused turns too, `on="thread"` to give the verdicts on the thread (sampling by thread), and `sinks=[OtelEventSink()]` to also emit them as OpenTelemetry evaluation events. Don't add a Langfuse score sink: the mirror already sends the feedback there.

### End-to-end measures

Drop-off and the rewrite rate are exact: `thread_sessions` and `artifact_histories` put a workspace's log into evalr's measure inputs.

```python
from datetime import UTC, datetime, timedelta

from evalr.measures import drop_off_evaluator, drop_off_rate, rewrite_evaluator, rewrite_rate

from artifactr.evals import artifact_histories, thread_sessions

window = timedelta(hours=1)
dropping = drop_off_evaluator(window=window, now=datetime.now(UTC))
drop_off = drop_off_rate([await dropping.evaluate(s) for s in await thread_sessions(workspace)])
rewriting = rewrite_evaluator(window=window)
rewrites = rewrite_rate([await rewriting.evaluate(h) for h in await artifact_histories(workspace)])
```

| Measure | From |
|---|---|
| Drop-off | Each thread's activity: every envelope in it, by people (`user` actors), agents (built-in or external) or the system. A thread dropped off when the agent acted last and nobody came back within the window, or when a proposal was left unresolved |
| Rewrite rate | Each artifact's versions, by whoever wrote their content. An accepted proposal is its proposer's; one accepted with the reviewer's changes is the agent's proposal and the person's rewrite of it at once. Archiving is not a version. The text is `render_for_agent()` unless you pass `text=` |

Task completion needs judgement. `TaskCompletion` is evalr's `TaskCompletion` as a feedback type (`completed`, `quality` from 1 to 5, `reason`), given on threads by people or evaluators. `completion_transcript` builds a DSPy judge's or a Jev decision model's input from a thread's transcript and the artifacts it followed:

```python
from evalr.dspy import DspyJudge
from evalr.measures import Transcript

from artifactr.evals import (
    LogFeedbackSource,
    OnlineEvaluator,
    TaskCompletion,
    completion_transcript,
)

judge = DspyJudge(TaskCompletion, inputs=Transcript, lm=lm)
completion = OnlineEvaluator([judge], input=completion_transcript, on="thread", sample_rate=0.2)
people = LogFeedbackSource(
    workspace, feedback_type=TaskCompletion, input_type=Transcript, input=completion_transcript
)
```

Importing `artifactr.evals` registers `TaskCompletion` as `task_completion`; evalr's `completion_rate` reads its verdicts. Long threads may need summarizing for a decision model's input budget, which is evalr's concern.
