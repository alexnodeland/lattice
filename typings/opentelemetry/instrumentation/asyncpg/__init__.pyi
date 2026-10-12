"""Minimal stubs for the parts of opentelemetry-instrumentation-asyncpg the libraries use."""

from collections.abc import Collection
from typing import Any, override

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor

class AsyncPGInstrumentor(BaseInstrumentor):
    def __init__(self, capture_parameters: bool = False) -> None: ...
    @override
    def instrumentation_dependencies(self) -> Collection[str]: ...
    @override
    def _instrument(self, **kwargs: Any) -> None: ...
    @override
    def _uninstrument(self, **kwargs: Any) -> None: ...
