"""An OpenTelemetry logger provider that keeps its records in memory."""

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.sdk._logs import LoggerProvider, ReadableLogRecord
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor


class Logs:
    def __init__(self) -> None:
        self.exporter = InMemoryLogRecordExporter()
        self.provider = LoggerProvider()
        self.provider.add_log_record_processor(SimpleLogRecordProcessor(self.exporter))

    def records(self) -> tuple[ReadableLogRecord, ...]:
        return self.exporter.get_finished_logs()


@contextmanager
def logs() -> Iterator[Logs]:
    kept = Logs()
    try:
        yield kept
    finally:
        kept.provider.shutdown()
