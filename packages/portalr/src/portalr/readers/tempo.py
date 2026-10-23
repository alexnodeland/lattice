"""Tempo: a tenant's traces and sessions, searched with TraceQL and filtered by tenant.

Every search names the tenant in TraceQL (``span.tenant.id``), and a trace read by its id is
shown only if one of its spans names the tenant and none names another.
"""

import asyncio
import base64
import binascii
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Annotated, Any, Final, Self

import httpx
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

from portalr.readers.http import read
from portalr.readers.query import MOST_DAYS, Id, Window, quoted
from portalr.readers.reading import Ok, Unavailable
from portalr.tenant import Tenant

TENANT_ATTRIBUTE: Final = "tenant.id"
"""The span attribute that names a span's tenant, which the collector copies from the libraries'
``artifactr.tenant.id`` and ``reflexr.tenant.id``."""

SESSION_ATTRIBUTE: Final = "session.id"
"""The span attribute that names a span's session: an artifactr thread."""

ANALYTICS_SESSION_ATTRIBUTE: Final = "portalr.analytics.session"
"""The server span attribute that names a request's analytics session (portalr ADR-0073), set
only where the session was the caller's own: a random id, of no one, never their user id. It is
safe to show, but to operators alone: :func:`for_tenant` takes it out of every other reader's."""

ANALYTICS_SESSION: Final = r"^\d{1,12}-[0-9a-f]{16}$"
"""An analytics session's id, as the relay makes it: when it began, and 16 random hex digits."""

RUN_ATTRIBUTES: Final = ("artifactr.run.id", "reflexr.run.id")
"""The span attributes that name a run, in either library."""


SAFE_ATTRIBUTES: Final = frozenset(
    {
        "tenant.id",
        "session.id",
        "user.id",
        ANALYTICS_SESSION_ATTRIBUTE,
        # artifactr's: ids, kinds, outcomes and counts, never text a person or a model wrote.
        "artifactr.actor.kind",
        "artifactr.artifact.id",
        "artifactr.artifact.kind",
        "artifactr.artifact.version",
        "artifactr.command.type",
        "artifactr.feedback.target",
        "artifactr.feedback.type",
        "artifactr.message.kind",
        "artifactr.outcome",
        "artifactr.patch.kind",
        "artifactr.patch.size",
        "artifactr.proposal.action",
        "artifactr.proposal.id",
        "artifactr.run.id",
        "artifactr.run.status",
        "artifactr.tenant.id",
        "artifactr.thread.id",
        "artifactr.tool.status",
        "artifactr.turn.outcome",
        "artifactr.turn.trigger",
        "artifactr.workspace.id",
        # reflexr's.
        "reflexr.actor.kind",
        "reflexr.attempt",
        "reflexr.event.count",
        "reflexr.event.duplicate",
        "reflexr.event.id",
        "reflexr.event.seq",
        "reflexr.event.type",
        "reflexr.feedback.target",
        "reflexr.feedback.type",
        "reflexr.rule",
        "reflexr.run.attempts",
        "reflexr.run.id",
        "reflexr.run.status",
        "reflexr.schedule",
        "reflexr.scope",
        "reflexr.tenant.id",
        "reflexr.workspace.id",
        # relayr's.
        "relayr.envelope.seq",
        "relayr.event.type",
        "relayr.tenant.id",
        "relayr.workspace.id",
        # The GenAI conventions' names and counts, but not their messages.
        "gen_ai.agent.name",
        "gen_ai.conversation.id",
        "gen_ai.operation.name",
        "gen_ai.provider.name",
        "gen_ai.request.max_tokens",
        "gen_ai.request.model",
        "gen_ai.request.temperature",
        "gen_ai.request.top_p",
        "gen_ai.response.finish_reasons",
        "gen_ai.response.id",
        "gen_ai.response.model",
        "gen_ai.system",
        "gen_ai.token.type",
        "gen_ai.tool.call.id",
        "gen_ai.tool.name",
        "gen_ai.tool.type",
        "gen_ai.workflow.name",
        "langfuse.observation.type",
        # What a request or a query was, not what it said.
        "http.request.method",
        "http.method",
        "http.response.status_code",
        "http.status_code",
        "http.route",
        "url.scheme",
        "server.address",
        "server.port",
        "network.protocol.name",
        "network.protocol.version",
        "db.system",
        "db.system.name",
        "db.operation.name",
        "db.collection.name",
        "db.namespace",
        # How a span ended, by its type, never its message.
        "exception.type",
        "error.type",
        "otel.status_code",
        "otel.scope.name",
        "otel.scope.version",
        "code.function",
        "code.function.name",
        "code.namespace",
    }
)
"""The span attributes a trace read shows without being asked: those known not to hold what a
person or a model said. Every other attribute is withheld, and named in the span's ``withheld``,
until a person asks for that span's (portalr ADR-0030): prompts and completions, tool arguments
and results, SQL, request and response bodies, an exception's message, and whatever a library or
a version adds later. The gate fails closed."""

SAFE_PREFIXES: Final = ("gen_ai.usage.",)
"""Whole families of attributes known to be counts and costs: token usage."""

MOST_NAME: Final = 200
"""The longest a span's name is shown: instrumentation sometimes puts a query or a URL in one."""

MOST_SPANS: Final = 5_000
"""The most spans a trace read gives: past it, the read says it isn't complete."""

DEADLINE: Final = 10.0
"""How long a trace read may take, in seconds, before Tempo is said not to have answered."""


def _safe(name: str, value: str | int | float | bool) -> bool:
    """Whether an attribute is known not to hold what was said.

    A name on the list is; one of a family of counts is only if its value is a number, so a
    crafted ``gen_ai.usage.prompt`` carrying text isn't.
    """
    if name in SAFE_ATTRIBUTES:
        return True
    counted = isinstance(value, int | float) and not isinstance(value, bool)
    return name.startswith(SAFE_PREFIXES) and counted


_TRACE_ID: Final = re.compile(r"[0-9a-fA-F]{1,31}")


def _padded(trace_id: str) -> str:
    """A trace's id as 32 lowercase hex digits, where it is hex; any other is left as it came.

    Tempo's search answers an id without its leading zeros.
    """
    return trace_id.zfill(32).lower() if _TRACE_ID.fullmatch(trace_id) else trace_id


type TraceId = Annotated[str, AfterValidator(_padded)]
"""A trace's id, whole."""

_SPAN_ID: Final = re.compile(r"[0-9a-fA-F]{16}")


def _hex(span_id: str) -> str:
    """A span's id as 16 lowercase hex digits: Tempo's OTLP JSON gives it in base64."""
    if _SPAN_ID.fullmatch(span_id):
        return span_id.lower()
    try:
        raw = base64.b64decode(span_id, validate=True)
    except binascii.Error:
        return span_id
    return raw.hex() if len(raw) == 8 else span_id


class TraceQuery(Window):
    """Which of a tenant's traces to find: a thread's, a run's, an analytics session's, or any.

    A search by analytics session reads at most ``MOST_DAYS``: a session lasts hours.
    """

    session: Id | None = None
    run: Id | None = None
    analytics_session: Annotated[str, StringConstraints(pattern=ANALYTICS_SESSION)] | None = None

    @model_validator(mode="after")
    def _a_sessions_window_is_bounded(self) -> Self:
        if self.analytics_session is not None and self.end - self.start > timedelta(days=MOST_DAYS):
            raise ValueError(f"a window is at most {MOST_DAYS} days")
        return self


class TraceSummary(BaseModel):
    """A trace Tempo found: its id, start and duration.

    Its root's service and name are left out, since the root may be another tenant's span.
    """

    model_config = ConfigDict(frozen=True)

    trace_id: TraceId = Field(validation_alias="traceID")
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
    withheld: tuple[str, ...] = ()
    """The names of the attributes the span has and this read left out, as they aren't known to
    be safe to show."""


class Trace(BaseModel):
    """A trace and its spans."""

    model_config = ConfigDict(frozen=True)

    trace_id: TraceId
    spans: tuple[Span, ...]
    complete: bool = True
    """False where the trace has more spans than ``MOST_SPANS``, and these are the first."""


class _Found(BaseModel):
    traces: list[TraceSummary] = []


_FOUND: Final = TypeAdapter(_Found)
_OTLP: Final = TypeAdapter(dict[str, Any])


def carries_analytics_session(trace: Trace) -> bool:
    """Whether a span of the trace names an analytics session."""
    return any(ANALYTICS_SESSION_ATTRIBUTE in span.attributes for span in trace.spans)


def for_tenant(trace: Trace) -> Trace:
    """The trace as one who isn't an operator reads it: without any span's analytics session."""
    spans = tuple(
        span.model_copy(
            update={
                "attributes": {
                    name: value
                    for name, value in span.attributes.items()
                    if name != ANALYTICS_SESSION_ATTRIBUTE
                },
                "withheld": tuple(n for n in span.withheld if n != ANALYTICS_SESSION_ATTRIBUTE),
            }
        )
        for span in trace.spans
    )
    return trace.model_copy(update={"spans": spans})


def search_query(tenant: Tenant, query: TraceQuery) -> str:
    """The TraceQL that finds a tenant's traces: always ``span.tenant.id``, then the filters."""
    conditions = [f"span.{TENANT_ATTRIBUTE} = {quoted(tenant.id)}"]
    if query.session is not None:
        conditions.append(f"span.{SESSION_ATTRIBUTE} = {quoted(query.session)}")
    if query.run is not None:
        runs = " || ".join(f"span.{name} = {quoted(query.run)}" for name in RUN_ATTRIBUTES)
        conditions.append(f"({runs})")
    found = "{ " + " && ".join(conditions) + " }"
    if query.analytics_session is None:
        return found
    # The session is on the server's span, the tenant on the libraries': each in the same trace.
    session = f"span.{ANALYTICS_SESSION_ATTRIBUTE} = {quoted(query.analytics_session)}"
    return f"{found} && {{ {session} }}"


def _plain(value: Mapping[str, Any]) -> Any:
    """An OTLP value as JSON holds it: a list or a map of them, or a scalar."""
    if "arrayValue" in value:
        return [_plain(each) for each in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return {
            pair["key"]: _plain(pair.get("value", {}))
            for pair in value["kvlistValue"].get("values", [])
        }
    for key in ("stringValue", "boolValue", "doubleValue"):
        if key in value:
            return value[key]
    return int(value.get("intValue", 0))


def _value(value: Mapping[str, Any]) -> str | int | float | bool:
    """An attribute's value: a scalar as it is, and a list or a map as its JSON."""
    plain = _plain(value)
    return json.dumps(plain) if isinstance(plain, list | dict) else plain


def _span(span: Mapping[str, Any]) -> Span:
    return Span(
        span_id=_hex(span["spanId"]),
        parent_id=_hex(span["parentSpanId"]) if span.get("parentSpanId") else None,
        name=span.get("name", "")[:MOST_NAME],
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


def _without_repeats(spans: list[Span]) -> list[Span]:
    """Each span once, the first: Tempo may answer one more than once, when its batches repeat."""
    once: dict[str, Span] = {}
    for span in spans:
        once.setdefault(span.span_id, span)
    return list(once.values())


def _withholding(spans: list[Span], reveal: str | None) -> list[Span]:
    """The spans with only their safe attributes, each naming what it withheld.

    The span ``reveal`` names keeps them all.
    """
    return [
        span
        if reveal is not None and span.span_id == reveal.lower()
        else span.model_copy(
            update={
                "attributes": {
                    name: value for name, value in span.attributes.items() if _safe(name, value)
                },
                "withheld": tuple(
                    sorted(
                        name for name, value in span.attributes.items() if not _safe(name, value)
                    )
                ),
            }
        )
        for span in spans
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

    async def trace(
        self, tenant: Tenant, trace_id: Id, *, reveal: str | None = None
    ) -> Ok[Trace | None] | Unavailable:
        """A trace by its id, if it is the tenant's; ``None`` if it isn't, or doesn't exist.

        Each span is once, and has only the attributes known to be safe, but for the span
        ``reveal`` names, which has all of its own. A trace has at most ``MOST_SPANS`` spans, and
        says if it has more; Tempo has ``DEADLINE`` seconds to answer.
        """
        try:
            async with asyncio.timeout(DEADLINE):
                document = await read(
                    self.client, "tempo", f"{self.url}/api/v2/traces/{trace_id}", _OTLP
                )
        except TimeoutError:
            return Unavailable(reason="tempo didn't answer in time")
        if isinstance(document, Unavailable):
            return document
        if document is None:
            return Ok(data=None)  # Tempo has no such trace
        spans = _spans(document)
        # Whose it is is settled over every span as Tempo gave it, before any is left out, even for
        # being a repeat: a span of another tenant's that reuses an id is still one.
        if not belongs(tenant, spans):
            return Ok(data=None)
        spans = _without_repeats(spans)
        shown = _withholding(spans[:MOST_SPANS], reveal)
        return Ok(
            data=Trace(trace_id=trace_id, spans=tuple(shown), complete=len(spans) <= MOST_SPANS)
        )
