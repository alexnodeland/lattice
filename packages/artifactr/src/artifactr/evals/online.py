"""Online evaluation: evalr's evaluators judge turns as they end; their verdicts are feedback.

An :class:`OnlineEvaluator` is a :class:`~artifactr.agent.TurnEvaluator`, the Runner's port for
judging turns (ADR-0044). It samples turns and keeps to a budget with evalr's
``OnlineEvaluation``, and records each verdict as feedback from an
:class:`~artifactr.core.EvaluatorActor`, through the one write path.
"""

import asyncio
import dataclasses
import logging
from collections.abc import Collection, Sequence
from inspect import isawaitable
from typing import Literal

from opentelemetry import context, trace
from pydantic import BaseModel

from artifactr.agent import EndedTurn, TurnOutcome
from artifactr.core import EvaluatorActor, Feedback, GiveFeedback, ThreadTarget, TurnTarget
from artifactr.evals.context import BuildTurnInput, target_context
from artifactr.workspace import Workspace
from evalr.core import Evaluator, ScoreSink, Verdict
from evalr.online import Budget, OnlineEvaluation, OnlineResult

logger = logging.getLogger("artifactr.evals")


class OnlineEvaluator[InputT: BaseModel]:
    """Judges a Runner's turns as they end, and records the verdicts as feedback.

    Give it to a Runner as one of its ``evaluators``::

        judging = OnlineEvaluator(
            [helpfulness_judge],
            input=turn_input,
            sample_rate=0.1,
            budget=Budget(max_cost=5.0),
        )
        runner = Runner(agent, app=deps, evaluators=[judging])

    When a turn ends, and it is sampled, the evaluator builds the input from the turn's
    :class:`~artifactr.evals.TargetContext` and has evalr judge it, in the background: the turn
    is neither slowed nor failed. Each verdict is given as feedback on the turn (or its thread)
    by an ``EvaluatorActor`` with the verdict's evaluator name and version, so a
    ``FeedbackMirror`` scores it like people's feedback, and the two can be compared.

    Sampling is by the run's id (the thread's, when judging threads), and the budget is spent
    per evaluation, both by evalr's ``OnlineEvaluation``. Failures are recorded on the results
    and logged on the ``artifactr.evals`` logger, never raised; an evaluator's own failure is
    also recorded on its span, in the turn's trace.

    Args:
        evaluators: evalr evaluators whose verdicts are feedback types that can be given on
            ``on``.
        input: Builds the evaluators' input from the turn's context.
        on: What the verdicts are about: the turn, or its whole thread.
        outcomes: The turns to judge, by how they ended; completed ones by default.
        sample_rate: The share of turns (or threads) to judge, from 0 to 1.
        budget: Limits evaluations and cost per period.
        sinks: Where every verdict's scores also go, such as evalr's ``OtelEventSink``. The
            verdicts are recorded as feedback either way, so a ``FeedbackMirror`` already
            sends them to Langfuse.
        salt: Changes which turns are sampled.
        max_concurrency: How many turns are judged at once.
    """

    def __init__(
        self,
        evaluators: Sequence[Evaluator[InputT, Feedback]],
        *,
        input: BuildTurnInput[InputT],
        on: Literal["turn", "thread"] = "turn",
        outcomes: Collection[TurnOutcome] = ("completed",),
        sample_rate: float = 1.0,
        budget: Budget | None = None,
        sinks: Sequence[ScoreSink] = (),
        salt: str = "artifactr-online",
        max_concurrency: int = 8,
    ) -> None:
        names: dict[type[BaseModel], str] = {
            e.verdict_type: e.verdict_type.feedback_type for e in evaluators
        }
        self.evaluation = OnlineEvaluation[InputT](
            evaluators,
            sample_rate=sample_rate,
            salt=salt,
            budget=budget,
            sinks=sinks,
            type_names=names,
            max_concurrency=max_concurrency,
        )
        """evalr's online evaluation, which samples, keeps the budget and judges."""
        self._input = input
        self._on = on
        self._outcomes = frozenset(outcomes)
        self._pending: set[asyncio.Task[OnlineResult]] = set()

    def submit(self, turn: EndedTurn) -> "asyncio.Task[OnlineResult] | None":
        """Judge a turn that ended in the background, if it is to be judged and is sampled.

        Returns:
            The evaluation, or ``None`` when the turn is not judged.
        """
        session = turn.session
        key = session.thread_id if self._on == "thread" else session.run_id
        if turn.outcome not in self._outcomes or not self.evaluation.sampled(key):
            return None
        task = asyncio.create_task(self._evaluate(turn, key))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return task

    async def drain(self) -> list[OnlineResult]:
        """Wait for every evaluation in progress, as when the application shuts down."""
        return list(await asyncio.gather(*self._pending))

    async def _evaluate(self, turn: EndedTurn, key: str) -> OnlineResult:
        # Everything the evaluation does, its commits included, is in the turn's trace.
        token = context.attach(trace.set_span_in_context(trace.NonRecordingSpan(turn.span)))
        try:
            result = await self._judge(turn, key)
        finally:
            context.detach(token)
        for error in result.errors:
            logger.warning("evaluating run %s failed: %s", turn.session.run_id, error)
        return result

    async def _judge(self, turn: EndedTurn, key: str) -> OnlineResult:
        session = turn.session
        try:
            about = await target_context(session.workspace, TurnTarget(run_id=session.run_id))
            built = self._input(about)
            judged = await built if isawaitable(built) else built
        except Exception as error:
            return OnlineResult(key=key, sampled=True, errors=(_describe("input", error),))
        result = await self.evaluation.submit(judged, key=key, span=turn.span)
        target = (
            ThreadTarget(thread_id=session.thread_id)
            if self._on == "thread"
            else TurnTarget(run_id=session.run_id)
        )
        errors: list[str] = []
        for verdict in result.verdicts:
            try:
                await _give(session.workspace, verdict, target)
            except Exception as error:
                errors.append(_describe(verdict.evaluator, error))
        return dataclasses.replace(result, errors=(*result.errors, *errors))


async def _give(
    workspace: Workspace, verdict: Verdict[BaseModel], target: ThreadTarget | TurnTarget
) -> None:
    """Give a verdict as feedback, from its evaluator's version."""
    value = verdict.value
    if not isinstance(value, Feedback):
        raise TypeError(f"{type(value).__name__} is not a feedback type")
    judge = workspace.as_actor(EvaluatorActor(name=verdict.evaluator, version=verdict.version))
    await judge.commit(
        GiveFeedback(
            feedback_type=value.feedback_type, target=target, value=value.model_dump(mode="json")
        )
    )


def _describe(what: str, error: Exception) -> str:
    return f"{what}: {type(error).__name__}: {error}"
