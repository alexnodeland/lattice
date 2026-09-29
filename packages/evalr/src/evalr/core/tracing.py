"""OpenTelemetry spans for evaluations, through the API only.

evalr never configures the OpenTelemetry SDK. Its spans go to the tracer provider an evaluator is
given, or the global one, under the ``evalr`` scope. With no SDK configured they cost nothing,
and a verdict records the trace of the span its evaluation ran in, when there is one.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import version as _distribution_version
from time import perf_counter

from opentelemetry import trace
from pydantic import BaseModel

from evalr.core.verdicts import Verdict

__all__ = [
    "ATTR_EVALUATOR_NAME",
    "ATTR_EVALUATOR_VERSION",
    "ATTR_VERDICT_TYPE",
    "SCOPE",
    "Judging",
    "current_trace_id",
    "get_tracer",
    "judging",
]

SCOPE = "evalr"
"""The instrumentation scope of evalr's spans."""

ATTR_EVALUATOR_NAME = "evalr.evaluator.name"
ATTR_EVALUATOR_VERSION = "evalr.evaluator.version"
ATTR_VERDICT_TYPE = "evalr.verdict.type"


def get_tracer(tracer_provider: trace.TracerProvider | None = None) -> trace.Tracer:
    """Return evalr's tracer from the given provider, or the global one.

    Args:
        tracer_provider: The provider to use. ``None`` uses the global provider, which is a
            no-op until the application configures the SDK.
    """
    return trace.get_tracer(SCOPE, _distribution_version("evalr"), tracer_provider=tracer_provider)


def current_trace_id() -> str | None:
    """Return the current span's trace id as 32 hex digits, or ``None`` outside any trace."""
    return _trace_id(trace.get_current_span())


def _trace_id(span: trace.Span) -> str | None:
    context = span.get_span_context()
    return trace.format_trace_id(context.trace_id) if context.is_valid else None


@dataclass(slots=True)
class Judging:
    """One evaluation in progress: its span and its clock.

    Evaluators build their verdict through ``verdict``, which stamps it with the evaluator, the
    latency so far and the trace id.
    """

    evaluator: str
    version: str
    span: trace.Span
    started: float

    def verdict[V: BaseModel](
        self,
        value: V,
        *,
        confidence: dict[str, float] | None = None,
        cost: float | None = None,
    ) -> Verdict[V]:
        """Wrap a value in a verdict from this evaluation.

        Args:
            value: The verdict type's instance.
            confidence: The probability that each field's value is right, where known.
            cost: What the evaluation cost in US dollars, where known.
        """
        return Verdict(
            value=value,
            confidence=confidence or {},
            evaluator=self.evaluator,
            version=self.version,
            latency=perf_counter() - self.started,
            cost=cost,
            trace_id=_trace_id(self.span),
        )


@contextmanager
def judging(
    tracer: trace.Tracer, *, evaluator: str, version: str, verdict_type: type[BaseModel]
) -> Generator[Judging]:
    """Run an evaluation in a span named ``evalr.evaluate {evaluator}``.

    The span is current inside the block, so the spans of whatever the evaluator calls (a
    language model, an agent) nest under it. An exception is recorded on the span and re-raised.

    Args:
        tracer: evalr's tracer, from ``get_tracer``.
        evaluator: The evaluator's name.
        version: The evaluator's version.
        verdict_type: The verdict type the evaluator returns.

    Yields:
        The evaluation in progress, whose ``verdict`` builds the result.
    """
    attributes = {
        ATTR_EVALUATOR_NAME: evaluator,
        ATTR_EVALUATOR_VERSION: version,
        ATTR_VERDICT_TYPE: verdict_type.__name__,
    }
    with tracer.start_as_current_span(f"evalr.evaluate {evaluator}", attributes=attributes) as span:
        yield Judging(evaluator=evaluator, version=version, span=span, started=perf_counter())
