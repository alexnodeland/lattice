"""Evaluation results as OpenTelemetry events, on the spans they judge.

Each score becomes a ``gen_ai.evaluation.result`` event, following the OpenTelemetry GenAI
conventions, emitted through the logs API with the judged trace and span as its context. Unlike an
event added to the span itself, it can be emitted after that span has ended, as online
evaluations are.
"""

from collections import defaultdict
from collections.abc import Sequence

from opentelemetry import trace
from opentelemetry._logs import LoggerProvider, get_logger
from opentelemetry.context import Context
from opentelemetry.util.types import AttributeValue

from evalr.core import SCOPE, Score

__all__ = ["EVALUATION_RESULT", "OtelEventSink"]

EVALUATION_RESULT = "gen_ai.evaluation.result"
"""The event's name in the OpenTelemetry GenAI conventions."""


class OtelEventSink:
    """Records scores as ``gen_ai.evaluation.result`` events, through the OpenTelemetry API.

    The events go to the logger provider given, or the global one, which is a no-op until the
    application configures the SDK, so evaluation data reaches any backend, not only one.

    - ``gen_ai.evaluation.name``: the score's name, ``{type}.{field}``
    - ``gen_ai.evaluation.score.value``: a number, or 1 or 0 for a yes or no
    - ``gen_ai.evaluation.score.label``: a choice, or ``true`` or ``false``
    - ``gen_ai.evaluation.explanation``: the verdict's text fields, such as its reason; a text
      field's own event has its text alone
    - ``evalr.evaluator.name``, ``evalr.evaluator.version``, ``evalr.score.id`` and
      ``evalr.confidence``: the rest

    Events are append-only; each carries its score's id, so a reader that keys by it keeps the
    latest.
    """

    def __init__(self, logger_provider: LoggerProvider | None = None) -> None:
        """Emit through a logger provider.

        Args:
            logger_provider: The provider; the global one by default.
        """
        self._logger = get_logger(SCOPE, logger_provider=logger_provider)

    async def record(self, scores: Sequence[Score], /) -> None:
        """Emit an event for each score."""
        explanations: dict[tuple[str, str, str | None, str | None], list[str]] = defaultdict(list)
        for score in scores:
            if score.data_type == "TEXT":
                explanations[_verdict(score)].append(f"{score.name.split('.')[-1]}: {score.value}")
        for score in scores:
            if score.data_type == "TEXT":
                explanation = str(score.value)
            else:
                explanation = "\n".join(explanations[_verdict(score)])
            self._logger.emit(
                event_name=EVALUATION_RESULT,
                context=_judged(score),
                attributes=_attributes(score, explanation),
            )


def _verdict(score: Score) -> tuple[str, str, str | None, str | None]:
    return score.evaluator, score.version, score.trace_id, score.span_id


def _judged(score: Score) -> Context | None:
    """The judged trace and span as a context: the score's, or the current one (``None``).

    A score with a trace but no span gives a context whose span id is 0, which carries the trace
    alone.
    """
    if score.trace_id is None:
        return None
    span = trace.SpanContext(
        trace_id=int(score.trace_id, 16),
        span_id=int(score.span_id, 16) if score.span_id else 0,
        is_remote=True,
        trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED),
    )
    return trace.set_span_in_context(trace.NonRecordingSpan(span))


def _attributes(score: Score, explanation: str) -> dict[str, AttributeValue]:
    attributes: dict[str, AttributeValue] = {
        "gen_ai.evaluation.name": score.name,
        "evalr.evaluator.name": score.evaluator,
        "evalr.evaluator.version": score.version,
        "evalr.score.id": score.id,
    }
    value = score.value
    if isinstance(value, bool):
        attributes["gen_ai.evaluation.score.value"] = 1.0 if value else 0.0
        attributes["gen_ai.evaluation.score.label"] = "true" if value else "false"
    elif score.data_type == "CATEGORICAL":
        attributes["gen_ai.evaluation.score.label"] = str(value)
    elif not isinstance(value, str):
        attributes["gen_ai.evaluation.score.value"] = float(value)
    if explanation:
        attributes["gen_ai.evaluation.explanation"] = explanation
    if score.confidence is not None:
        attributes["evalr.confidence"] = score.confidence
    return attributes
