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

## What comes next

RFC-0002 plans two more pieces on top of feedback:

- the `[langfuse]` extra mirrors feedback to Langfuse as scores on the traces it judges
- the `[evals]` extra connects artifactr to evalr, the shared eval kit, for datasets from the log, experiments, online evaluators and end-to-end measures such as rewrite rate and drop-off
