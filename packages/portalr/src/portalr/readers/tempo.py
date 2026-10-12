"""Tempo: a tenant's traces and sessions, searched with TraceQL and filtered by tenant.

Every search names the tenant in TraceQL (``span.tenant.id``), and a trace read by its id is
shown only if one of its spans names the tenant and none names another.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from portalr.readers.http import read
from portalr.readers.query import Id, Window, quoted
from portalr.readers.reading import Ok, Unavailable
from portalr.tenant import Tenant

TENANT_ATTRIBUTE: Final = "tenant.id"
"""The span attribute that names a span's tenant, which the collector copies from the libraries'
``artifactr.tenant.id`` and ``reflexr.tenant.id``."""

SESSION_ATTRIBUTE: Final = "session.id"
"""The span attribute that names a span's session: an artifactr thread."""

RUN_ATTRIBUTES: Final = ("artifactr.run.id", "reflexr.run.id")
"""The span attributes that name a run, in either library."""


class TraceQuery(Window):
    """Which of a tenant's traces to find: a session's, a run's, or any, in a window."""

    session: Id | None = None
    run: Id | None = None


class TraceSummary(BaseModel):
    """A trace Tempo found: its id, start and duration.

    Its root's service and name are left out, since the root may be another tenant's span.
    """

    model_config = ConfigDict(frozen=True)

    trace_id: str = Field(validation_alias="traceID")
    root_service: str | None = Field(default=None, validation_alias="rootServiceName")
    root_name: str | None = Field(default=None, validation_alias="rootTraceName")
    start_ns: int = Field(validation_alias="startTimeUnixNano")
    duration_ms: int | None = Field(default=None, validation_alias="durationMs")


class Span(BaseModel):
    """One span of a trace, with its attributes flattened to values."""

    model_config = ConfigDict(frozen=True)

    span_id: str
    parent_id: str | None
    name: str
    start_ns: int
    end_ns: int
    attributes: Mapping[str, str | int | float | bool]
    error: bool


class Trace(BaseModel):
    """A trace and its spans."""

    model_config = ConfigDict(frozen=True)

    trace_id: str
    spans: tuple[Span, ...]


class _Found(BaseModel):
    traces: list[TraceSummary] = []


_FOUND: Final = TypeAdapter(_Found)
_OTLP: Final = TypeAdapter(dict[str, Any])


def search_query(tenant: Tenant, query: TraceQuery) -> str:
    """The TraceQL that finds a tenant's traces: always ``span.tenant.id``, then the filters."""
    conditions = [f"span.{TENANT_ATTRIBUTE} = {quoted(tenant.id)}"]
    if query.session is not None:
        conditions.append(f"span.{SESSION_ATTRIBUTE} = {quoted(query.session)}")
    if query.run is not None:
        runs = " || ".join(f"span.{name} = {quoted(query.run)}" for name in RUN_ATTRIBUTES)
        conditions.append(f"({runs})")
    return "{ " + " && ".join(conditions) + " }"


def _value(value: Mapping[str, Any]) -> str | int | float | bool:
    for key in ("stringValue", "boolValue", "doubleValue"):
        if key in value:
            return value[key]
    return int(value.get("intValue", 0))


def _span(span: Mapping[str, Any]) -> Span:
    return Span(
        span_id=span["spanId"],
        parent_id=span.get("parentSpanId") or None,
        name=span.get("name", ""),
        start_ns=int(span.get("startTimeUnixNano", 0)),
        end_ns=int(span.get("endTimeUnixNano", 0)),
        attributes={
            attribute["key"]: _value(attribute.get("value", {}))
            for attribute in span.get("attributes", [])
        },
        error=span.get("status", {}).get("code") == "STATUS_CODE_ERROR",
    )


def _spans(document: Mapping[str, Any]) -> list[Span]:
    """The spans of a trace, as Tempo's v2 API answers it in OpenTelemetry's JSON."""
    trace = document.get("trace", document)
    return [
        _span(span)
        for resource in trace.get("resourceSpans", [])
        for scope in resource.get("scopeSpans", [])
        for span in scope.get("spans", [])
    ]


def belongs(tenant: Tenant, spans: list[Span]) -> bool:
    """Whether a trace is the tenant's: one span names it, and none names another."""
    named = {
        str(span.attributes[TENANT_ATTRIBUTE])
        for span in spans
        if TENANT_ATTRIBUTE in span.attributes
    }
    return named == {tenant.id}


@dataclass(frozen=True)
class Tempo:
    """Reads traces from Tempo's HTTP API.

    Args:
        url: Tempo's HTTP API, such as ``http://tempo:3200``.
        client: The HTTP client to send requests with.
    """

    url: str
    client: httpx.AsyncClient = field(default_factory=httpx.AsyncClient)

    async def search(
        self, tenant: Tenant, query: TraceQuery
    ) -> Ok[list[TraceSummary]] | Unavailable:
        """The tenant's traces that match the query, newest first."""
        found = await read(
            self.client,
            "tempo",
            f"{self.url}/api/search",
            _FOUND,
            params={
                "q": search_query(tenant, query),
                "start": int(query.start.timestamp()),
                "end": int(query.end.timestamp()),
                "limit": query.limit,
            },
        )
        if found is None or isinstance(found, Unavailable):
            return found or Unavailable(reason="tempo has no search API at that address")
        # A trace's root may be another tenant's span: its service and name aren't shown here,
        # and reading the trace applies the rule below.
        traces = [
            trace.model_copy(update={"root_service": None, "root_name": None})
            for trace in found.traces
        ]
        return Ok(data=sorted(traces, key=lambda trace: trace.start_ns, reverse=True))

    async def trace(self, tenant: Tenant, trace_id: Id) -> Ok[Trace | None] | Unavailable:
        """A trace by its id, if it is the tenant's; ``None`` if it isn't, or doesn't exist."""
        document = await read(self.client, "tempo", f"{self.url}/api/v2/traces/{trace_id}", _OTLP)
        if isinstance(document, Unavailable):
            return document
        if document is None:
            return Ok(data=None)  # Tempo has no such trace
        spans = _spans(document)
        return Ok(
            data=Trace(trace_id=trace_id, spans=tuple(spans)) if belongs(tenant, spans) else None
        )
