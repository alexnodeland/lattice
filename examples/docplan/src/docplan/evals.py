"""Evaluating docplan: from people's feedback to a judge, online verdicts, replays and measures.

The agent is told to keep its edits small, and people say when it did not: an
:class:`~docplan.artifacts.EditSize` on the turn, given with ``/edits`` in the terminal client.

1. :func:`dataset` turns that feedback into an evalr dataset. :func:`turn_edits` builds each
   example's input from the turn as it ended: what was asked, and the docs before and after.
2. :func:`edit_size_judge` judges the same input with a function, and :func:`calibrate` picks
   its threshold by agreement with people. With ``DOCPLAN_JUDGE_MODEL`` set (and the ``dspy``
   extra installed), :func:`judge_from_environment` is a DSPy judge instead.
3. :func:`online_from_environment` has the server judge a share of its turns as they end, when
   ``DOCPLAN_EVAL_SAMPLE_RATE`` is set, and records each verdict as feedback from the judge.
4. :func:`replay` replays the dataset's turns against an agent, and judges what it does.
5. :func:`measures` computes task completion, drop-off and the rewrite rate from the log.

``docplan-eval`` (:mod:`docplan.evaluate`) runs the steps against the server's database.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from artifactr import Session, Workspace
from artifactr.core import (
    ArtifactChanged,
    ArtifactCreated,
    FeedbackGiven,
    MessagePosted,
    TurnTarget,
)
from artifactr.evals import (
    LogFeedbackSource,
    OnlineEvaluator,
    Replay,
    Seed,
    TargetContext,
    TaskCompletion,
    actor_role,
    artifact_histories,
    replay_task,
    target_context,
    thread_sessions,
)
from docplan.artifacts import Doc, EditSize, Plan
from evalr import (
    Dataset,
    Evaluator,
    Example,
    ExperimentResult,
    FunctionEvaluator,
    Measurement,
    collect,
    measure,
    optimize,
)
from evalr.measures import (
    Turn,
    completion_rate,
    drop_off_evaluator,
    drop_off_rate,
    rewrite_evaluator,
    rewrite_rate,
    share_changed,
)
from evalr.memory import BestOf, InMemoryExperimentTracker
from evalr.online import Budget

THRESHOLDS = (0.25, 0.5, 0.75)
"""The function judge's thresholds that :func:`calibrate` chooses from."""


class TurnEdits(BaseModel):
    """What an edit-size judge reads: a turn's request, and the thread's docs before and after.

    Plans are left out: the agent's changes to them are proposals, which people review anyway.
    """

    history: list[Turn] = Field(
        default_factory=list[Turn], description="The thread's messages before the request"
    )
    request: str = Field(description="The person's message that started the turn")
    before: dict[str, Doc] = Field(
        default_factory=dict[str, Doc],
        description="The docs as the turn started, by id; not those it created",
    )
    after: dict[str, Doc] = Field(
        default_factory=dict[str, Doc], description="The docs as the turn ended, by id"
    )
    reply: str | None = Field(default=None, description="The agent's last message in the turn")


async def turn_edits(context: TargetContext) -> TurnEdits:
    """Build the judge's input from a turn's context.

    It is the input builder for the dataset, for online evaluation and for replays, so the
    judge reads the same thing in each.
    """
    start = context.events[0].seq  # the turn's run_started
    said = [
        (envelope.seq, Turn(role=actor_role(envelope.actor), text=envelope.event.content))
        for envelope in context.transcript
        if isinstance(envelope.event, MessagePosted)
    ]
    earlier = [turn for seq, turn in said if seq < start]
    replies = [turn.text for seq, turn in said if seq > start and turn.role == "agent"]
    after = {doc.id: doc.data for doc in context.artifacts if isinstance(doc.data, Doc)}
    before: dict[str, Doc] = {}
    for doc_id, doc in after.items():
        if (started := await _as_the_turn_started(context, doc_id, doc)) is not None:
            before[doc_id] = started
    return TurnEdits(
        history=earlier[:-1],
        request=earlier[-1].text,
        before=before,
        after=after,
        reply=replies[-1] if replies else None,
    )


async def _as_the_turn_started(context: TargetContext, doc_id: str, ended: Doc) -> Doc | None:
    """A doc as the turn started: the version before the turn first changed it.

    ``None`` if the turn created it, and ``ended`` if the turn did not change it.
    """
    written = [
        envelope.event.version
        for envelope in context.events
        if isinstance(envelope.event, ArtifactCreated | ArtifactChanged)
        and envelope.event.artifact_id == doc_id
    ]
    if not written:
        return ended
    if min(written) == 1:
        return None
    revisions = await context.workspace.revisions(doc_id)
    [revision] = [r for r in revisions if r.version == min(written) - 1]
    return Doc.model_validate(revision.data)


def changed(turn: TurnEdits) -> float:
    """The most of any one doc the turn changed, from 0 to 1, as evalr's ``share_changed``.

    Docs the turn created do not count, and docs it dropped changed entirely.
    """
    most = 0.0
    for doc_id, doc in turn.before.items():
        ended = turn.after.get(doc_id, Doc())
        most = max(most, share_changed(doc.render_for_agent(), ended.render_for_agent()))
    return most


def edit_size_judge(threshold: float = 0.5) -> FunctionEvaluator[TurnEdits, EditSize]:
    """A function judge: the edits were too big if they changed more than ``threshold`` of a doc.

    Docs the turn created do not count: a first draft is never too big. The threshold is part of
    the version, so verdicts from different thresholds never mix.
    """

    def edit_size(turn: TurnEdits) -> EditSize:
        return EditSize(too_big=changed(turn) > threshold)

    return FunctionEvaluator(
        edit_size, verdict_type=EditSize, name="edit-size", version=f"1:{threshold:g}"
    )


def dspy_judge(model: str) -> Evaluator[TurnEdits, EditSize]:
    """A DSPy judge of edit size on a language model, such as ``openai/gpt-5-mini``.

    It reads the request as well as the docs, so it can tell a rewrite that was asked for from
    one that was not. It needs docplan's ``dspy`` extra, so DSPy is imported only here.
    """
    import dspy

    from evalr.dspy import DspyJudge

    return DspyJudge(EditSize, inputs=TurnEdits, name="edit-size-judge", lm=dspy.LM(model))


def judge_from_environment() -> Evaluator[TurnEdits, EditSize]:
    """The judge the environment asks for.

    A DSPy judge on ``DOCPLAN_JUDGE_MODEL`` when it is set; otherwise the function judge, at
    ``DOCPLAN_JUDGE_THRESHOLD`` (0.5 by default).
    """
    if model := os.environ.get("DOCPLAN_JUDGE_MODEL"):
        return dspy_judge(model)
    return edit_size_judge(float(os.environ.get("DOCPLAN_JUDGE_THRESHOLD", "0.5")))


def online_from_environment() -> OnlineEvaluator[TurnEdits] | None:
    """Judge a share of the server's turns as they end, when ``DOCPLAN_EVAL_SAMPLE_RATE`` is set.

    Each verdict is recorded as edit-size feedback from the judge, beside people's.
    ``DOCPLAN_EVAL_BUDGET`` caps the evaluations a day (1000 by default).
    """
    rate = os.environ.get("DOCPLAN_EVAL_SAMPLE_RATE")
    if not rate:
        return None
    return OnlineEvaluator(
        [judge_from_environment()],
        input=turn_edits,
        sample_rate=float(rate),
        budget=Budget(max_evaluations=int(os.environ.get("DOCPLAN_EVAL_BUDGET", "1000"))),
    )


async def dataset(workspace: Workspace) -> Dataset[TurnEdits, EditSize]:
    """People's edit-size feedback in a workspace, as an evalr dataset.

    The judge's own verdicts are left out: it must not be measured against itself.
    """
    source = LogFeedbackSource(
        workspace, feedback_type=EditSize, input_type=TurnEdits, input=turn_edits
    )
    return await collect("docplan-edit-size", source)


async def calibrate(
    judge: Evaluator[TurnEdits, EditSize], examples: Dataset[TurnEdits, EditSize]
) -> tuple[Evaluator[TurnEdits, EditSize], Measurement[EditSize]]:
    """Choose the judge that agrees best with people, and measure it on turns held out.

    The candidates are ``judge`` and the function judge at each of :data:`THRESHOLDS`; a tie
    keeps ``judge``. With too few examples to hold some out, ``judge`` is measured on them all.

    Returns:
        The judge chosen, and how far it agrees with people.
    """
    train, validate = examples.labelled().split(0.3)
    if not train or not validate:
        return judge, await measure(judge, examples)
    candidates = BestOf([edit_size_judge(threshold) for threshold in THRESHOLDS])
    chosen = await optimize(judge, train=train, validate=validate, optimizer=candidates)
    return chosen, candidates.measurements[-1]


def seed(example: Example[TurnEdits, EditSize]) -> Seed:
    """The thread as the example's turn started: its messages, and its docs then."""
    turn = example.input
    return Seed(prompt=turn.request, messages=turn.history, artifacts=turn.before)


async def replayed(replay: Replay) -> TurnEdits:
    """What a replayed turn did, read as a live turn is, so the same judge judges it."""
    context = await target_context(replay.workspace, TurnTarget(run_id=replay.run.id))
    return await turn_edits(context)


async def replay(
    agent: Agent[Session[None], Any],
    examples: Dataset[TurnEdits, EditSize],
    judge: Evaluator[TurnEdits, EditSize],
) -> ExperimentResult[TurnEdits]:
    """Replay each example's turn against ``agent`` in an isolated workspace, and judge it."""
    task = replay_task(
        agent, app=None, seed=seed, output=replayed, types=[Doc, Plan], agent_name="docplan"
    )
    return await InMemoryExperimentTracker().run_experiment(
        "docplan-edit-size", dataset=examples, task=task, evaluators=[judge]
    )


@dataclass(frozen=True)
class Measures:
    """docplan's end-to-end measures, each a share from 0 to 1, or ``None`` without data.

    Attributes:
        completion: Of the threads people (or a judge) said were done or not, the share done,
            by the latest word on each.
        drop_off: Of the threads decided, the share where the agent was left waiting.
        rewrites: Of the agent's versions of docs and plans, the share a person substantially
            rewrote soon after.
    """

    completion: float | None
    drop_off: float | None
    rewrites: float | None


async def measures(workspace: Workspace, *, window: timedelta, now: datetime) -> Measures:
    """Measure task completion, drop-off and the rewrite rate from a workspace's log.

    Args:
        workspace: The workspace.
        window: How long a person has to come back to the agent, or to rewrite what it wrote.
        now: When the log is read, for drop-off.
    """
    dropping = drop_off_evaluator(window=window, now=now)
    rewriting = rewrite_evaluator(window=window)
    latest = {
        envelope.thread_id: TaskCompletion.model_validate(envelope.event.value)
        for envelope in await workspace.read()
        if isinstance(envelope.event, FeedbackGiven)
        and envelope.event.feedback_type == TaskCompletion.feedback_type
    }
    return Measures(
        completion=completion_rate(latest.values()),
        drop_off=drop_off_rate(
            [await dropping.evaluate(s) for s in await thread_sessions(workspace)]
        ),
        rewrites=rewrite_rate(
            [await rewriting.evaluate(h) for h in await artifact_histories(workspace)]
        ),
    )
