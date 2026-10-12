"""Minimal stubs for the parts of opentelemetry-instrumentation-sqlalchemy the libraries use."""

from collections.abc import Collection
from typing import Any, override

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor

class SQLAlchemyInstrumentor(BaseInstrumentor):
    @override
    def instrumentation_dependencies(self) -> Collection[str]: ...
    @override
    def _instrument(self, **kwargs: Any) -> Any: ...
    @override
    def _uninstrument(self, **kwargs: Any) -> None: ...
