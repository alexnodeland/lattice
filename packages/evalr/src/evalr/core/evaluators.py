"""Evaluators that are plain functions, and the composition that hands off between two."""

import hashlib
import inspect
from collections.abc import Awaitable, Callable

from opentelemetry import trace
from pydantic import BaseModel

from evalr.core.fields import verdict_fields
from evalr.core.ports import Evaluator
from evalr.core.tracing import ATTR_EVALUATOR_NAME, ATTR_EVALUATOR_VERSION, get_tracer, judging
from evalr.core.verdicts import Verdict

__all__ = ["Fallback", "FunctionEvaluator", "HandOff"]


class HandOff(Exception):
    """An evaluator declines to judge an input, for another evaluator to judge instead.

    A decision model raises it when it is unsure, or cannot fill a field; ``Fallback`` catches
    it and asks its fallback.
    """


class FunctionEvaluator[InputT: BaseModel, VerdictT: BaseModel]:
    """An evaluator that is a function of its input: a deterministic measure.

    The function may be sync or async. Its version is given, not derived: change it whenever the
    function's behaviour changes.

    Example:
        ```python
        def resolved(thread: Thread) -> Resolution:
            return Resolution(resolved=thread.messages[-1].author == "user")


        evaluator = FunctionEvaluator(resolved, verdict_type=Resolution, version="2")
        verdict = await evaluator.evaluate(thread)
        ```
    """

    def __init__(
        self,
        function: Callable[[InputT], VerdictT | Awaitable[VerdictT]],
        *,
        verdict_type: type[VerdictT],
        name: str | None = None,
        version: str = "1",
        tracer_provider: trace.TracerProvider | None = None,
    ) -> None:
        """Wrap a function as an evaluator.

        Args:
            function: Computes the verdict's value from the input.
            verdict_type: The Pydantic model the function returns.
            name: The evaluator's name; the function's name by default.
            version: The evaluator's version; bump it when the function changes.
            tracer_provider: Where evaluation spans go; the global provider by default.

        Raises:
            UnsupportedField: The verdict type has a field evaluators cannot judge.
        """
        verdict_fields(verdict_type)
        self._function = function
        self._verdict_type = verdict_type
        self._name = name or function.__name__
        self._version = version
        self._tracer = get_tracer(tracer_provider)

    @property
    def name(self) -> str:
        """The evaluator's name."""
        return self._name

    @property
    def version(self) -> str:
        """The evaluator's version."""
        return self._version

    @property
    def verdict_type(self) -> type[VerdictT]:
        """The verdict type."""
        return self._verdict_type

    async def evaluate(self, input: InputT, /) -> Verdict[VerdictT]:
        """Run the function on the input.

        Raises:
            TypeError: The function returned something other than the verdict type.
        """
        with judging(
            self._tracer,
            evaluator=self._name,
            version=self._version,
            verdict_type=self._verdict_type,
        ) as run:
            result = self._function(input)
            value = await result if inspect.isawaitable(result) else result
            if not isinstance(value, self._verdict_type):
                raise TypeError(
                    f"{self._name} returned {type(value).__name__}, "
                    f"not {self._verdict_type.__name__}"
                )
            return run.verdict(value)


class Fallback[InputT: BaseModel, VerdictT: BaseModel]:
    """Two evaluators of one verdict type: the primary judges, and hands off to the fallback.

    The primary hands off by raising ``HandOff``, or, when ``min_confidence`` is set, by giving a
    verdict with any field's confidence below it. The usual pairing is a fast, cheap decision
    model first and a language-model judge behind it:

    ```python
    evaluator = Fallback(DecisionEvaluator(...), DspyJudge(...), min_confidence=0.7)
    ```

    Each verdict records the evaluator that actually gave it, so the two are measured apart.
    The composition runs in a span named ``evalr.fallback {name}``, which records whether and
    why it handed off.
    """

    def __init__(
        self,
        primary: Evaluator[InputT, VerdictT],
        fallback: Evaluator[InputT, VerdictT],
        *,
        min_confidence: float | None = None,
        name: str | None = None,
        tracer_provider: trace.TracerProvider | None = None,
    ) -> None:
        """Compose two evaluators.

        Args:
            primary: Judges first.
            fallback: Judges what the primary hands off.
            min_confidence: Hand off a verdict with any field's confidence below this.
            name: The composition's name; ``{primary}+{fallback}`` by default.
            tracer_provider: Where the composition's spans go; the global provider by default.

        Raises:
            TypeError: The two evaluators' verdict types differ.
            ValueError: ``min_confidence`` is outside ``[0, 1]``.
        """
        if primary.verdict_type is not fallback.verdict_type:
            raise TypeError(
                f"{primary.name} gives {primary.verdict_type.__name__} but {fallback.name} gives "
                f"{fallback.verdict_type.__name__}"
            )
        if min_confidence is not None and not 0.0 <= min_confidence <= 1.0:
            raise ValueError(f"min_confidence must be between 0 and 1; got {min_confidence}")
        self.primary = primary
        self.fallback = fallback
        self.min_confidence = min_confidence
        self._name = name or f"{primary.name}+{fallback.name}"
        parts = (
            f"{primary.name}@{primary.version}|{fallback.name}@{fallback.version}|{min_confidence}"
        )
        self._version = hashlib.sha256(parts.encode()).hexdigest()[:12]
        self._tracer = get_tracer(tracer_provider)

    @property
    def name(self) -> str:
        """The composition's name."""
        return self._name

    @property
    def version(self) -> str:
        """A hash of both evaluators' names and versions, and the threshold."""
        return self._version

    @property
    def verdict_type(self) -> type[VerdictT]:
        """The verdict type both evaluators give."""
        return self.primary.verdict_type

    async def evaluate(self, input: InputT, /) -> Verdict[VerdictT]:
        """Ask the primary, and the fallback if the primary hands off."""
        attributes = {ATTR_EVALUATOR_NAME: self._name, ATTR_EVALUATOR_VERSION: self._version}
        with self._tracer.start_as_current_span(
            f"evalr.fallback {self._name}", attributes=attributes
        ) as span:
            try:
                verdict = await self.primary.evaluate(input)
            except HandOff as handoff:
                reason = f"{self.primary.name} handed off: {handoff}"
            else:
                unsure = self._unsure(verdict)
                if unsure is None:
                    span.set_attribute("evalr.fallback.handed_off", False)
                    return verdict
                reason = f"{self.primary.name} was unsure of {unsure}"
            span.set_attributes(
                {"evalr.fallback.handed_off": True, "evalr.fallback.reason": reason}
            )
            return await self.fallback.evaluate(input)

    def _unsure(self, verdict: Verdict[VerdictT]) -> str | None:
        """The least confident field, if its confidence is below the threshold."""
        if self.min_confidence is None or not verdict.confidence:
            return None
        field, confidence = min(verdict.confidence.items(), key=lambda item: item[1])
        return field if confidence < self.min_confidence else None
