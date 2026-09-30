"""Evaluation results as OpenTelemetry events, on the spans they judge.

Each score becomes a ``gen_ai.evaluation.result`` event, following the OpenTelemetry GenAI
conventions, emitted through the logs API with the judged trace and span as its context. Unlike an
event added to the span itself, it can be emitted after that span has ended, as online
evaluations are.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from opentelemetry import trace
from opentelemetry._logs import LoggerProvider, get_logger
from opentelemetry.context import Context
from opentelemetry.util.types import AttributeValue

from evalr.core import SCOPE, Score
from evalr.core._explanation import explanation

__all__ = ["EVALUATION_RESULT", "OtelEventSink"]

EVALUATION_RESULT = "gen_ai.evaluation.result"
"""The event's name in the OpenTelemetry GenAI conventions."""

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

type _Verdict = tuple[str | None, str | None, str | None, str | None]
"""What a score's verdict is keyed by: the evaluator, its version, the trace and the span."""


class OtelEventSink:
    """Records scores as ``gen_ai.evaluation.result`` events, through the OpenTelemetry API.

    The events go to the logger provider given, or the global one, which is a no-op until the
    application configures the SDK, so evaluation data reaches any backend, not only one.

    - ``gen_ai.evaluation.name``: the score's name, ``{type}.{field}``
    - ``gen_ai.evaluation.score.value``: a number, or 1 or 0 for a yes or no
    - ``gen_ai.evaluation.score.label``: a choice, or ``true`` or ``false``
    - ``gen_ai.evaluation.explanation``: the verdict's text fields, such as its reason; a text
      field's own event has its text alone
    - ``session.id``: the session the score is attached to, when it has one
    - ``evalr.evaluator.name``, ``evalr.evaluator.version``, ``evalr.score.id`` and
      ``evalr.confidence``: the rest, where the score has them (people's feedback has no
      evaluator)
    - ``evalr.source.{key}``: each entry of the score's source, such as who gave the feedback.
      Entries are emitted verbatim and may identify people or tenants, so put nothing in a
      score's source that the log pipeline must not hold.

    An event's time is the score's timestamp, when it has one. Events are append-only; each
    carries its score's id, so a reader that keys by it keeps the latest.
    """

    def __init__(self, logger_provider: LoggerProvider | None = None) -> None:
        """Emit through a logger provider.

        Args:
            logger_provider: The provider; the global one by default.
        """
        self._logger = get_logger(SCOPE, logger_provider=logger_provider)

    async def record(self, scores: Sequence[Score], /) -> None:
        """Emit an event for each score."""
        verdicts: dict[_Verdict, list[Score]] = defaultdict(list)
        for score in scores:
            verdicts[_verdict(score)].append(score)
        for score in scores:
            if score.data_type == "TEXT":
                explained = str(score.value)
            else:
                explained = explanation(verdicts[_verdict(score)])
            self._logger.emit(
                timestamp=_nanoseconds(score.timestamp) if score.timestamp else None,
                event_name=EVALUATION_RESULT,
                context=_judged(score),
                attributes=_attributes(score, explained),
            )


def _verdict(score: Score) -> _Verdict:
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


def _attributes(score: Score, explained: str) -> dict[str, AttributeValue]:
    attributes: dict[str, AttributeValue] = {
        "gen_ai.evaluation.name": score.name,
        "evalr.score.id": score.id,
    }
    if score.session_id is not None:
        attributes["session.id"] = score.session_id
    if score.evaluator is not None:
        attributes["evalr.evaluator.name"] = score.evaluator
    if score.version is not None:
        attributes["evalr.evaluator.version"] = score.version
    if score.data_type == "BOOLEAN":
        attributes["gen_ai.evaluation.score.value"] = 1.0 if score.value else 0.0
        attributes["gen_ai.evaluation.score.label"] = "true" if score.value else "false"
    elif score.data_type == "NUMERIC":
        attributes["gen_ai.evaluation.score.value"] = float(score.value)
    elif score.data_type == "CATEGORICAL":
        attributes["gen_ai.evaluation.score.label"] = str(score.value)
    if explained:
        attributes["gen_ai.evaluation.explanation"] = explained
    if score.confidence is not None:
        attributes["evalr.confidence"] = score.confidence
    for key, value in score.source.items():
        attributes[f"evalr.source.{key}"] = value
    return attributes


def _nanoseconds(moment: datetime) -> int:
    """A time as nanoseconds since the epoch, as OpenTelemetry records it."""
    return (moment - _EPOCH) // timedelta(microseconds=1) * 1_000
