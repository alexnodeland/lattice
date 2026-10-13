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
    Contribution,
    Instrumented,
    LangfuseMode,
    TelemetryContribution,
    TelemetryHandle,
    installed,
    redact_access_token,
)
from lattice_core.otel.configure import configure_telemetry as _configure_telemetry
from reflexr.telemetry import METRICS, SCOPE, MetricsDetail, is_trace_scope, kept_attributes

__all__ = [
    "BAGGAGE_KEYS",
    "INSTRUMENTED",
    "URL_ATTRIBUTES",
    "Contribution",
    "Instrumented",
    "LangfuseMode",
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
    """Set up OpenTelemetry for an application: providers, OTLP export and instrumentation.

    Call it once, as early as the application starts, before it creates its FastAPI app and
    agents, with the contributions of the other libraries the application uses, such as
    ``artifactr.otel.telemetry()``; reflexr's own is always included. artifactr's
    ``configure_telemetry`` takes the same contributions and does the same. It sets up:

    - tracer, meter and logger providers, with ``service.name``, ``service.version`` and
      ``deployment.environment.name`` on their resource
    - OTLP over HTTP to ``otlp_endpoint``, or to the endpoint the ``OTEL_EXPORTER_OTLP_*``
      environment variables name (a local Collector by default)
    - every contribution's views, which apply each library's metric cardinality policy at
      ``metrics_detail``
    - a baggage processor that copies a run attempt's session, its causal chain, onto every
      span in it
    - the open instrumentations the contributions advise (FastAPI, SQLAlchemy, httpx and
      httpx2), or those ``instrument`` names, with the stable HTTP semantic conventions
      (``OTEL_SEMCONV_STABILITY_OPT_IN=http``, unless it is set already)
    - pydantic-ai's instrumentation settings, which :meth:`TelemetryHandle.capability` wraps
      for an agent
    - with ``langfuse``, a Langfuse client on the same tracer provider (``reflexr.langfuse``,
      the ``[langfuse]`` extra), which sends Langfuse whole traces, or only scores

    Nothing in reflexr requires it: it is one way to configure the SDK, which reflexr
    only ever records to through the API.

    Args:
        *contributions: Other libraries' contributions (:class:`TelemetryContribution`), or
            the application's own. One is kept per name, the first given, and reflexr's own,
            :func:`telemetry`, is added unless one is named ``reflexr``.
        service_name: The service's name, as it appears in every backend.
        service_version: The service's version.
        environment: The deployment environment, such as ``production``.
        otlp_endpoint: The OTLP/HTTP base URL, such as ``http://collector:4318``. Defaults to
            the ``OTEL_EXPORTER_OTLP_ENDPOINT`` environment variable.
        otlp_headers: Headers for every OTLP request, such as a backend's credentials.
        instrument: Which libraries to instrument. Defaults to those the contributions advise
            that are installed.
        engines: SQLAlchemy engines that already exist, to trace their queries.
        include_content: Whether pydantic-ai records prompts, completions and tool arguments.
        metrics_detail: How much tenancy detail the libraries' metrics keep.
        logs: Whether to export the ``logging`` module's records through OTLP.
        span_exporter: Where spans go instead of OTLP, such as an in-memory exporter in tests.
        metric_reader: How metrics are read instead of a periodic OTLP export.
        log_exporter: Where log records go instead of OTLP.
        span_processors: More span processors to add, such as a backend's own.
        langfuse: What the application sends Langfuse itself (:data:`LangfuseMode`):
            ``"traces"``, with a span filter that keeps a span any contribution keeps, and
            Langfuse's own LLM spans; or ``"scores"``, when the Collector sends Langfuse the
            traces. Its keys come from the ``LANGFUSE_*`` environment variables or
            ``langfuse_options``.
        langfuse_options: Passed to ``Langfuse(...)``; a ``should_export_span`` here replaces
            the filter ``langfuse`` chooses.
        set_global: Whether to make the providers the global ones, which reflexr, pydantic-ai
            and the instrumentations default to.

    Returns:
        A handle that shuts it all down.
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
