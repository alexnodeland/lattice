"""Loki: a tenant's logs, read with LogQL, filtered by tenant, and shown without their lines.

Every query filters on the ``tenant_id`` structured metadata, where Loki keeps the collector's
``tenant.id``, and every record is checked for it again, before anything else is done with it. A
log line can hold what a person or a model said, so a read gives a record's time, level, service,
thread, run and the length of its line, and the labels known to be safe, and withholds the line
and every other label, naming them. One record's line is read apart, by its id, when asked for
(portalr ADR-0031).
"""

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Annotated, Final, Self

import httpx
from pydantic import BaseModel, ConfigDict, StringConstraints, TypeAdapter, model_validator

from portalr.readers.http import read
from portalr.readers.query import ID, Id, Window, nanoseconds, quoted
from portalr.readers.reading import Ok, Unavailable
from portalr.tenant import Tenant

TENANT_METADATA: Final = "tenant_id"
"""The structured metadata that names a log record's tenant: the collector's ``tenant.id``."""

THREAD_METADATA: Final = "artifactr_thread_id"
"""The structured metadata that names a log record's thread."""

RUN_METADATA: Final = ("artifactr_run_id", "reflexr_run_id")
"""The structured metadata that names a log record's run, in either library."""

EVERY_STREAM: Final = '{service_name=~".+"}'
"""LogQL needs a stream selector; the tenant is filtered after it, on every stream."""

SAFE_LABELS: Final = frozenset(
    {
        "service_name",
        "service_namespace",
        "service_version",
        "deployment_environment_name",
        "deployment_environment",
        "detected_level",
        "severity_text",
        "severity_number",
        "scope_name",
        "scope_version",
        "tenant_id",
        "artifactr_tenant_id",
        "artifactr_workspace_id",
        "artifactr_thread_id",
        "artifactr_run_id",
        "artifactr_actor_kind",
        "artifactr_command_type",
        "reflexr_tenant_id",
        "reflexr_workspace_id",
        "reflexr_run_id",
        "reflexr_rule",
        "reflexr_event_type",
        "trace_id",
        "span_id",
    }
)
"""The labels a log read shows without being asked: ids, names of services and loggers, and a
severity. Every other label, such as an attribute a library or an application added to a record,
is withheld and named in the record's ``withheld``: the gate fails closed (portalr ADR-0031)."""

IDS: Final = frozenset(name for name in SAFE_LABELS if name.endswith("_id"))
"""The safe labels that hold an id: their values must be one, as a query takes ids (``ID``)."""

NUMBERS: Final = frozenset({"severity_number"})
"""The safe labels that hold a number."""

LEVELS: Final = frozenset(
    {"trace", "debug", "info", "warn", "warning", "error", "fatal", "critical"}
)
"""The levels a record may be shown at; Loki derives ``detected_level`` from a line's own words,
and a level it gives that isn't one of these is withheld (portalr ADR-0031)."""

LEVEL_LABELS: Final = frozenset({"detected_level", "severity_text"})
"""The safe labels that hold a level."""

NAME: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.:@/+-]{0,127}$")
"""What a service's, a scope's or a library's name or version may be: short, and plain."""

MOST_HOURS: Final = 24
"""The longest window a log read takes, in hours."""

DEADLINE: Final = 10.0
"""How long a log read may take, in seconds, before Loki is said not to have answered."""

MOST_SAME_INSTANT: Final = 1000
"""The most records a read for one nanosecond looks through, to find the one asked for."""

RECORD_ID: Final = r"^[0-9]{1,19}-[0-9a-f]{16}-[0-9]{1,3}$"
"""A record's id: its time in nanoseconds, a digest of its stream's safe labels, and its place
among the records of that stream at that instant. Nothing in it comes from the line."""

_RECORD_ID: Final = re.compile(r"^([0-9]{1,19})-([0-9a-f]{16})-([0-9]{1,3})$")

INT64_MAX: Final = 2**63 - 1
"""The largest time Loki takes, in nanoseconds."""

type RecordId = Annotated[str, StringConstraints(pattern=RECORD_ID)]
"""A record's id, as :func:`_identify` makes it."""


class LogQuery(Window):
    """Which of a tenant's logs to read: a thread's, a run's, or any, within a day."""

    thread: Id | None = None
    run: Id | None = None

    @model_validator(mode="after")
    def _within_most_hours(self) -> Self:
        if self.end - self.start > timedelta(hours=MOST_HOURS):
            raise ValueError(f"a window is at most {MOST_HOURS} hours")
        return self


class LogRecord(BaseModel):
    """One log record, without its line unless that was asked for."""

    model_config = ConfigDict(frozen=True)

    id: str
    time_ns: int
    level: str | None
    service: str | None
    thread: str | None
    run: str | None
    length: int
    """How many characters the line has."""
    labels: dict[str, str]
    """The labels known to be safe to show."""
    withheld: tuple[str, ...] = ()
    """The names of the labels the record has and this read left out."""
    line: str | None = None
    """The line itself: only when it was asked for, for this record alone."""


class Logs(BaseModel):
    """A window's records, newest first, and whether they are all of them."""

    model_config = ConfigDict(frozen=True)

    records: list[LogRecord]
    complete: bool
    """False where Loki gave as many as were asked for: there may be more."""


class _Stream(BaseModel):
    stream: dict[str, str]
    values: list[tuple[str, str] | tuple[str, str, dict[str, str]]]


class _Data(BaseModel):
    result: list[_Stream] = []


class _Answer(BaseModel):
    data: _Data


_ANSWER: Final = TypeAdapter(_Answer)


def tenant_records_query(tenant: Tenant) -> str:
    """The LogQL that reads a tenant's records: always ``tenant_id``."""
    return f"{EVERY_STREAM} | {TENANT_METADATA} = {quoted(tenant.id)}"


def logs_query(tenant: Tenant, query: LogQuery) -> str:
    """The LogQL that reads a tenant's logs: ``tenant_id`` first, then the filters, if any."""
    stages: list[str] = []
    if query.thread is not None:
        stages.append(f"{THREAD_METADATA} = {quoted(query.thread)}")
    if query.run is not None:
        stages.append(" or ".join(f"{name} = {quoted(query.run)}" for name in RUN_METADATA))
    return tenant_records_query(tenant) + "".join(f" | {stage}" for stage in stages)


@dataclass(frozen=True)
class Loki:
    """Reads logs from Loki's HTTP API.

    Args:
        url: Loki's HTTP API, such as ``http://loki:3100``.
        client: The HTTP client to send requests with.
    """

    url: str
    client: httpx.AsyncClient = field(default_factory=httpx.AsyncClient)

    async def _query(
        self, tenant: Tenant, query: str, start: int, end: int, limit: int
    ) -> list[tuple[int, str, dict[str, str]]] | Unavailable:
        """The tenant's records of a LogQL query in a window, as (time, line, labels).

        They are those Loki says are the tenant's, which each is checked to be, before anything
        else is done with it.
        """
        try:
            async with asyncio.timeout(DEADLINE):
                answer = await read(
                    self.client,
                    "loki",
                    f"{self.url}/loki/api/v1/query_range",
                    _ANSWER,
                    params={
                        "query": query,
                        "start": start,
                        "end": end,
                        "limit": limit,
                        "direction": "backward",
                    },
                )
        except TimeoutError:
            return Unavailable(reason="loki didn't answer in time")
        if answer is None or isinstance(answer, Unavailable):
            return answer or Unavailable(reason="loki has no query API at that address")
        return [
            (int(value[0]), value[1], stream.stream)
            for stream in answer.data.result
            for value in stream.values
            if stream.stream.get(TENANT_METADATA) == tenant.id
        ]

    async def logs(self, tenant: Tenant, query: LogQuery) -> Ok[Logs] | Unavailable:
        """The tenant's log records that match the query, newest first, without their lines.

        A record has the labels known to be safe, and names the rest; its line is read apart, by
        its id (:meth:`record`). Past ``query.limit`` records there may be more, and the read says
        it isn't complete.
        """
        found = await self._query(
            tenant,
            logs_query(tenant, query),
            nanoseconds(query.start),
            nanoseconds(query.end),
            query.limit,
        )
        if isinstance(found, Unavailable):
            return found
        newest = sorted(_identify(found), key=lambda each: each[0].time_ns, reverse=True)
        return Ok(
            data=Logs(
                records=[each for each, _ in newest[: query.limit]],
                complete=len(found) < query.limit,
            )
        )

    async def record(self, tenant: Tenant, record_id: str) -> Ok[LogRecord | None] | Unavailable:
        """One of the tenant's records by its id, with its line.

        ``None`` if it isn't the tenant's, isn't there, or the id isn't one.
        """
        named = _RECORD_ID.fullmatch(record_id)
        if named is None or int(named[1]) >= INT64_MAX:
            return Ok(data=None)
        at = int(named[1])
        found = await self._query(
            tenant, tenant_records_query(tenant), at, at + 1, MOST_SAME_INSTANT
        )
        if isinstance(found, Unavailable):
            return found
        asked = next((each for each in _identify(found) if each[0].id == record_id), None)
        return Ok(data=asked and asked[0].model_copy(update={"line": asked[1]}))


def _stream(labels: dict[str, str]) -> str:
    """A stream's identity for an id: a digest of its safe labels, which a read shows anyway."""
    safe = "\x1f".join(f"{name}={labels[name]}" for name in sorted(labels) if name in SAFE_LABELS)
    return hashlib.sha256(safe.encode()).hexdigest()[:16]


def _identify(
    found: list[tuple[int, str, dict[str, str]]],
) -> list[tuple[LogRecord, str]]:
    """Each record, with its id, and its line.

    An id is made of what a read shows, and nothing of the line, so that holding an id and
    guessing a line can't confirm the guess: the time, the digest of the stream's safe labels, and
    the record's place among those of that stream at that instant. Places are counted in the order
    Loki gave the records, after ordering them by their labels, so they hold while Loki gives a
    window's records in the same order, and a read of one nanosecond is a window of its own.
    """
    places: dict[tuple[int, str], int] = {}
    made: list[tuple[LogRecord, str]] = []
    for time_ns, line, labels in sorted(found, key=lambda each: (each[0], sorted(each[2].items()))):
        stream = _stream(labels)
        place = places.get((time_ns, stream), 0)
        places[time_ns, stream] = place + 1
        made.append((_record(f"{time_ns}-{stream}-{place}", time_ns, line, labels), line))
    return made


def _safe(name: str, value: str) -> str | None:
    """A label's value as a read may show it, or ``None`` if it isn't plain enough to be."""
    if name in LEVEL_LABELS:
        return value.lower() if value.lower() in LEVELS else None
    if name in NUMBERS:
        return value if value.isascii() and value.isdigit() and len(value) <= 3 else None
    if name in IDS:
        return value if re.fullmatch(ID, value) else None
    return value if NAME.fullmatch(value) else None


def _record(record_id: str, time_ns: int, line: str, labels: dict[str, str]) -> LogRecord:
    """A record as a read shows it: its safe labels, the names of the rest, its line's length.

    A label is safe if its name is, and its value is short and plain: an id, a known level, a
    name. One that isn't is withheld with the rest. The line is added apart, for one record.
    """
    shown = {
        name: value
        for name, raw in labels.items()
        if name in SAFE_LABELS and (value := _safe(name, raw)) is not None
    }
    level = next(
        (shown[name] for name in ("detected_level", "severity_text") if name in shown), None
    )
    return LogRecord(
        id=record_id,
        time_ns=time_ns,
        level=level,
        service=shown.get("service_name"),
        thread=shown.get(THREAD_METADATA),
        run=shown.get("artifactr_run_id") or shown.get("reflexr_run_id"),
        length=len(line),
        labels=shown,
        withheld=tuple(sorted(set(labels) - set(shown))),
    )
