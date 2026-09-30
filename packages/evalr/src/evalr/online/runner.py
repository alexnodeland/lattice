"""Running evaluators on live traffic: sampled, within a budget, and on the judged span."""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from opentelemetry import context, trace
from pydantic import BaseModel

from evalr.core import Evaluator, HandOff, ScoreSink, Verdict, scores, split_bucket
from evalr.online.budgets import Budget

__all__ = ["OnlineEvaluation", "OnlineResult"]


@dataclass(frozen=True, slots=True)
class OnlineResult:
    """What happened to one live input.

    Attributes:
        key: The input's key, such as a run or turn id.
        sampled: Whether it was chosen for evaluation.
        verdicts: The verdicts given, in the evaluators' order.
        skipped: Evaluators left out because the budget was spent.
        handed_off: Evaluators that handed the input off, with nothing to hand it to.
        errors: What failed: an evaluator or a sink, by name, with its message.
    """

    key: str
    sampled: bool
    verdicts: tuple[Verdict[BaseModel], ...] = ()
    skipped: tuple[str, ...] = ()
    handed_off: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


class OnlineEvaluation[InputT: BaseModel]:
    """Runs evaluators on live inputs, as an application serves them.

    - **Sampling** is by the input's key: an input is judged when ``split_bucket(key, salt)`` is
      below ``sample_rate``, so the same run or turn is always judged or always not, in any
      process.
    - **Budget:** with a ``Budget``, evaluators run only while it allows, and spend it.
    - **The judged span:** evaluations run inside the trace of the span they judge (the current
      span when ``judge`` or ``submit`` is called, or the one given), so their spans nest under
      it even after it ended, and their scores are recorded on it.
    - **Sinks** receive every verdict's scores: Langfuse, OpenTelemetry events, or both.

    Failures are recorded on the result, never raised: online evaluation must not break the
    application it watches.

    Example:
        ```python
        online = OnlineEvaluation(
            [Fallback(decider, judge)],
            sample_rate=0.1,
            budget=Budget(max_cost=5.0),
            sinks=[LangfuseScoreSink(langfuse), OtelEventSink()],
        )
        online.submit(transcript, key=turn_id)  # in the background
        ```
    """

    def __init__(
        self,
        evaluators: Sequence[Evaluator[InputT, BaseModel]],
        *,
        sample_rate: float = 1.0,
        salt: str = "evalr-online",
        budget: Budget | None = None,
        sinks: Sequence[ScoreSink] = (),
        type_names: Mapping[type[BaseModel], str] | None = None,
        max_concurrency: int = 8,
    ) -> None:
        """Configure online evaluation.

        Args:
            evaluators: What judges each input, in order.
            sample_rate: The share of inputs to judge, from 0 to 1.
            salt: Changes which inputs are sampled.
            budget: Limits evaluations and cost per period.
            sinks: Where every verdict's scores go.
            type_names: Score names for verdict types, where a library registers its feedback
                under a name other than the class name in snake case.
            max_concurrency: How many inputs ``submit`` judges at once.

        Raises:
            ValueError: The sample rate is not between 0 and 1.
        """
        if not 0.0 <= sample_rate <= 1.0:
            raise ValueError(f"sample_rate must be between 0 and 1; got {sample_rate}")
        self.evaluators = tuple(evaluators)
        self.sample_rate = sample_rate
        self.salt = salt
        self.budget = budget
        self.sinks = tuple(sinks)
        self.type_names = dict(type_names or {})
        self._limit = asyncio.Semaphore(max_concurrency)
        self._pending: set[asyncio.Task[OnlineResult]] = set()

    def sampled(self, key: str) -> bool:
        """Whether an input with this key is judged."""
        return split_bucket(key, self.salt) < self.sample_rate

    async def judge(
        self, input: InputT, *, key: str, span: trace.SpanContext | None = None
    ) -> OnlineResult:
        """Judge one live input now, if it is sampled.

        Args:
            input: What to judge.
            key: The input's stable key, such as its run or turn id.
            span: The span it judges; the current span by default.
        """
        if not self.sampled(key):
            return OnlineResult(key=key, sampled=False)
        judged = span or trace.get_current_span().get_span_context()
        token = context.attach(trace.set_span_in_context(trace.NonRecordingSpan(judged)))
        try:
            return await self._judge(input, key, judged)
        finally:
            context.detach(token)

    def submit(
        self, input: InputT, *, key: str, span: trace.SpanContext | None = None
    ) -> "asyncio.Task[OnlineResult]":
        """Judge one live input in the background, at most ``max_concurrency`` at once.

        The judged span is taken now, so it is the one current when the input was submitted.
        """
        judged = span or trace.get_current_span().get_span_context()

        async def limited() -> OnlineResult:
            async with self._limit:
                return await self.judge(input, key=key, span=judged)

        task = asyncio.create_task(limited())
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return task

    async def drain(self) -> list[OnlineResult]:
        """Wait for everything submitted, as when the application shuts down."""
        return list(await asyncio.gather(*self._pending))

    async def _judge(self, input: InputT, key: str, judged: trace.SpanContext) -> OnlineResult:
        verdicts: list[Verdict[BaseModel]] = []
        skipped: list[str] = []
        handed_off: list[str] = []
        errors: list[str] = []
        for evaluator in self.evaluators:
            if self.budget is not None and not self.budget.allows():
                skipped.append(evaluator.name)
                continue
            try:
                verdict = await evaluator.evaluate(input)
            except HandOff:
                self._spend(None)
                handed_off.append(evaluator.name)
                continue
            except Exception as error:
                self._spend(None)
                errors.append(_describe(evaluator.name, error))
                continue
            self._spend(verdict.cost)
            verdicts.append(verdict)
            recorded = scores(
                verdict,
                type_name=self.type_names.get(type(verdict.value)),
                subject=key,
                trace_id=trace.format_trace_id(judged.trace_id) if judged.is_valid else None,
                span_id=trace.format_span_id(judged.span_id) if judged.is_valid else None,
            )
            for sink in self.sinks:
                try:
                    await sink.record(recorded)
                except Exception as error:
                    errors.append(_describe(type(sink).__name__, error))
        return OnlineResult(
            key=key,
            sampled=True,
            verdicts=tuple(verdicts),
            skipped=tuple(skipped),
            handed_off=tuple(handed_off),
            errors=tuple(errors),
        )

    def _spend(self, cost: float | None) -> None:
        if self.budget is not None:
            self.budget.spend(cost)


def _describe(what: str, error: Exception) -> str:
    return f"{what}: {type(error).__name__}: {error}"
