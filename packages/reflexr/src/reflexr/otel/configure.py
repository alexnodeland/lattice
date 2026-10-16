"""``configure_telemetry``: the OpenTelemetry SDK, exporters and instrumentations in one call.

lattice-core holds the setup the libraries share (lattice ADR-0018); this module adds reflexr's own
contribution to it, and re-exports the rest. The instrumentations import the libraries they
instrument, so each is imported only when it is used: an application that does not use FastAPI
or SQLAlchemy does not need them installed.
"""

from collections.abc import Collection, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final

from opentelemetry.sdk._logs.export import LogRecordExporter
from opentelemetry.sdk.metrics.export import MetricReader
from opentelemetry.sdk.metrics.view import View
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter

from lattice_core.otel.configure import (
    BAGGAGE_KEYS,
    INSTRUMENTED,
    URL_ATTRIBUTES,
    LangfuseMode,
    TelemetryHandle,
    installed,
    redact_access_token,
)
from lattice_core.otel.configure import configure_telemetry as _configure_telemetry
from lattice_core.otel.contribution import (
    Contribution,
    Instrumented,
    TelemetryContribution,
)
from reflexr.telemetry import METRICS, SCOPE, MetricsDetail, is_trace_scope, kept_attributes

__all__ = [
    "BAGGAGE_KEYS",
    "INSTRUMENTED",
    "URL_ATTRIBUTES",
    "Contribution",
    "Instrumented",
    "LangfuseMode",
    "MetricsDetail",
    "TelemetryContribution",
    "TelemetryHandle",
    "configure_telemetry",
    "installed",
    "metric_views",
    "redact_access_token",
    "telemetry",
]

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine

_ADVISED: Final[frozenset[Instrumented]] = frozenset({"fastapi", "sqlalchemy", "httpx"})
"""The instrumentations that trace reflexr's work: its surfaces, its SQL storage and its runs'
model calls. Not asyncpg as well as SQLAlchemy, which would record every query twice."""


def telemetry() -> Contribution:
    """Return reflexr's contribution, for any library's ``configure_telemetry``.

    Its views apply reflexr's metric cardinality policy, its span filter keeps the scopes in
    ``reflexr.telemetry.TRACE_SCOPES``, and it advises the FastAPI, SQLAlchemy and httpx
    instrumentations.
    """
    return Contribution(
        name=SCOPE,
        metric_views=metric_views,
        should_export_span=_in_reflexrs_traces,
        instrument=_ADVISED,
    )


def metric_views(detail: MetricsDetail = "workspace") -> list[View]:
    """Return views that keep only the attributes reflexr's metrics may carry at ``detail``.

    Pass them to the SDK's ``MeterProvider(views=...)``. With ``"tenant"`` the workspace is
    dropped, and with ``"none"`` both tenant and workspace are, before aggregation, so a
    deployment with many workspaces keeps a bounded number of series.
    """
    return [
        View(
            instrument_name=metric.name,
            meter_name=SCOPE,
            attribute_keys=set(kept_attributes(metric, detail)),
        )
        for metric in METRICS.values()
    ]


def _in_reflexrs_traces(span: ReadableSpan) -> bool:
    return is_trace_scope(span.instrumentation_scope.name if span.instrumentation_scope else "")


def configure_telemetry(
    *contributions: TelemetryContribution,
    service_name: str,
    service_version: str | None = None,
    environment: str | None = None,
    otlp_endpoint: str | None = None,
    otlp_headers: Mapping[str, str] | None = None,
    instrument: Collection[Instrumented] | None = None,
    engines: "Sequence[AsyncEngine | Engine]" = (),
    include_content: bool = False,
    metrics_detail: MetricsDetail = "workspace",
    logs: bool = True,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
    log_exporter: LogRecordExporter | None = None,
    span_processors: Sequence[SpanProcessor] = (),
    langfuse: LangfuseMode | None = None,
    langfuse_options: Mapping[str, Any] | None = None,
    set_global: bool = True,
) -> TelemetryHandle:
    """Set up OpenTelemetry for an application, with reflexr's contribution added last.

    Call it once, with the other libraries' contributions; it takes lattice-core's
    :func:`~lattice_core.otel.configure.configure_telemetry` arguments, and returns its handle.
    """
    return _configure_telemetry(
        *contributions,
        telemetry(),
        service_name=service_name,
        service_version=service_version,
        environment=environment,
        otlp_endpoint=otlp_endpoint,
        otlp_headers=otlp_headers,
        instrument=instrument,
        engines=engines,
        include_content=include_content,
        metrics_detail=metrics_detail,
        logs=logs,
        span_exporter=span_exporter,
        metric_reader=metric_reader,
        log_exporter=log_exporter,
        span_processors=span_processors,
        langfuse=langfuse,
        langfuse_options=langfuse_options,
        set_global=set_global,
    )
