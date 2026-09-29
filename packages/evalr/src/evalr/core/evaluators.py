"""Evaluators that are plain functions."""

import inspect
from collections.abc import Awaitable, Callable

from opentelemetry import trace
from pydantic import BaseModel

from evalr.core.fields import verdict_fields
from evalr.core.tracing import get_tracer, judging
from evalr.core.verdicts import Verdict

__all__ = ["FunctionEvaluator"]


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
