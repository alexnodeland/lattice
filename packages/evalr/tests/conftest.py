from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanContext


@dataclass
class Spans:
    provider: TracerProvider
    exporter: InMemorySpanExporter

    def finished(self) -> tuple[ReadableSpan, ...]:
        return self.exporter.get_finished_spans()


def context_of(span: ReadableSpan) -> SpanContext:
    assert span.context is not None
    return span.context


@pytest.fixture
def spans() -> Iterator[Spans]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield Spans(provider, exporter)
    provider.shutdown()
