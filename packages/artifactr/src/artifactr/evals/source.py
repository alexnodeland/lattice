"""A feedback source for evalr: the feedback in a workspace's log, as examples (ADR-0044)."""

from collections.abc import AsyncIterator, Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass
from inspect import isawaitable

from evalr.core import Example
from pydantic import BaseModel

from artifactr.core import Envelope, EvaluatorActor, Feedback, FeedbackGiven, TargetKind
from artifactr.evals.context import TargetContext, read_context
from artifactr.workspace import Workspace


@dataclass(frozen=True, kw_only=True)
class FeedbackContext[VerdictT: Feedback](TargetContext):
    """One piece of feedback, with the context of what it is about.

    It is a :class:`TargetContext` with the feedback added, so an input builder written for
    target contexts, such as an online evaluator's, builds dataset inputs too.

    Attributes:
        envelope: The ``feedback_given`` envelope: who gave the feedback, and when.
        feedback: The feedback, validated as its type.
    """

    envelope: Envelope
    feedback: VerdictT


type BuildInput[InputT, VerdictT: Feedback] = Callable[
    [FeedbackContext[VerdictT]], InputT | Awaitable[InputT]
]
"""Turns a piece of feedback's context into an evaluator's input; sync or async."""


class LogFeedbackSource[InputT: BaseModel, VerdictT: Feedback]:
    """Yields an example for each piece of one feedback type in a workspace's log.

    It is an evalr ``FeedbackSource``. The verdict is the feedback, and the input is built by
    the application from what the feedback is about, since only it knows what its evaluators
    judge. Example ids are the ids of the feedback's envelopes, so they are stable, and an
    example carries the trace of what it judges, where there is one.

    Evaluators' feedback is left out unless ``include_evaluators`` is set: online evaluators
    record their verdicts as feedback of the same types, and a judge must not be trained or
    calibrated on its own verdicts.

    Args:
        workspace: The workspace whose log to read.
        feedback_type: The feedback type to collect: the verdict type.
        input_type: The evaluator's input type.
        input: Builds an input from a piece of feedback's context.
        targets: Only feedback on these kinds of target; every kind by default.
        include_evaluators: Also collect the feedback evaluators gave, such as to compare their
            verdicts with people's.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        feedback_type: type[VerdictT],
        input_type: type[InputT],
        input: BuildInput[InputT, VerdictT],
        targets: Collection[TargetKind] | None = None,
        include_evaluators: bool = False,
    ) -> None:
        self._workspace = workspace
        self._feedback_type = feedback_type
        self._input_type = input_type
        self._input = input
        self._targets = targets
        self._include_evaluators = include_evaluators

    @property
    def input_type(self) -> type[InputT]:
        """The evaluator's input type."""
        return self._input_type

    @property
    def verdict_type(self) -> type[VerdictT]:
        """The feedback type, which is the verdict type."""
        return self._feedback_type

    async def examples(self) -> AsyncIterator[Example[InputT, VerdictT]]:
        """Yield an example for each piece of the feedback type, oldest first."""
        log = await self._workspace.read()
        for envelope in log:
            event = envelope.event
            if not isinstance(event, FeedbackGiven):
                continue
            if event.feedback_type != self._feedback_type.feedback_type:
                continue
            if self._targets is not None and event.target.kind not in self._targets:
                continue
            if isinstance(envelope.actor, EvaluatorActor) and not self._include_evaluators:
                continue
            yield await self._example(envelope, event, log)

    async def _example(
        self, envelope: Envelope, event: FeedbackGiven, log: Sequence[Envelope]
    ) -> Example[InputT, VerdictT]:
        feedback = self._feedback_type.model_validate(event.value)
        context = await read_context(self._workspace, event.target, log, limit=envelope.seq - 1)
        about = FeedbackContext(**vars(context), envelope=envelope, feedback=feedback)
        built = self._input(about)
        value = await built if isawaitable(built) else built
        return Example[InputT, VerdictT](
            id=envelope.id,
            input=self._input_type.model_validate(value),
            verdict=feedback,
            trace_id=context.trace_id,
            metadata={
                "tenant_id": self._workspace.tenant_id,
                "workspace_id": self._workspace.workspace_id,
                "thread_id": envelope.thread_id,
                "target": event.target.kind,
                "given_by": envelope.actor.participant,
                "seq": envelope.seq,
            },
        )
