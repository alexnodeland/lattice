"""Span filters for a Langfuse client: the ``langfuse`` extra."""

from collections.abc import Callable

from langfuse.span_filter import is_default_export_span
from opentelemetry.sdk.trace import ReadableSpan

__all__ = ["no_spans", "span_filter"]


def span_filter(*keeps: Callable[[ReadableSpan], bool]) -> Callable[[ReadableSpan], bool]:
    """Return a span filter that keeps Langfuse's LLM spans and every span one of ``keeps`` keeps.

    ``configure_telemetry(langfuse="traces")`` builds its filter this way, from the libraries'
    contributions, so an application of several libraries keeps each one's spans.
    """

    def keep(span: ReadableSpan) -> bool:
        return is_default_export_span(span) or any(kept(span) for kept in keeps)

    return keep


def no_spans(span: ReadableSpan) -> bool:
    """Keep no spans: the filter for a client that only sets trace attributes and sends scores.

    ``configure_telemetry(langfuse="scores")`` uses it when a Collector sends Langfuse every
    trace already, so no span arrives twice. The client's span processor still sets each
    session, user and tags on the spans, which reach Langfuse through the Collector.
    """
    del span
    return False
