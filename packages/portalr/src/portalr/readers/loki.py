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
from typing import Final, Self

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter, model_validator

from portalr.readers.http import read
from portalr.readers.query import Id, Window, quoted
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

MOST_HOURS: Final = 24
"""The longest window a log read takes, in hours."""

DEADLINE: Final = 10.0
"""How long a log read may take, in seconds, before Loki is said not to have answered."""

MOST_SAME_INSTANT: Final = 100
"""The most records a read for one nanosecond looks through, to find the one asked for."""

RECORD_ID: Final = re.compile(r"^(\d{1,20})-([0-9a-f]{16})$")
"""A record's id: its time in nanoseconds, then a digest of its stream and its line."""


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


def logs_query(tenant: Tenant, query: LogQuery | None) -> str:
    """The LogQL that reads a tenant's logs: always ``tenant_id``, then the filters, if any."""
    stages = [f"{TENANT_METADATA} = {quoted(tenant.id)}"]
    if query is None:
        return EVERY_STREAM + f" | {stages[0]}"
    if query.thread is not None:
        stages.append(f"{THREAD_METADATA} = {quoted(query.thread)}")
    if query.run is not None:
        stages.append(" or ".join(f"{name} = {quoted(query.run)}" for name in RUN_METADATA))
    return EVERY_STREAM + "".join(f" | {stage}" for stage in stages)


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
            int(query.start.timestamp() * 1_000_000_000),
            int(query.end.timestamp() * 1_000_000_000),
            query.limit,
        )
        if isinstance(found, Unavailable):
            return found
        newest = sorted(found, key=lambda record: record[0], reverse=True)
        return Ok(
            data=Logs(
                records=[_record(*each) for each in newest[: query.limit]],
                complete=len(found) < query.limit,
            )
        )

    async def record(self, tenant: Tenant, record_id: str) -> Ok[LogRecord | None] | Unavailable:
        """One of the tenant's records by its id, with its line.

        ``None`` if it isn't the tenant's, isn't there, or the id isn't one.
        """
        named = RECORD_ID.fullmatch(record_id)
        if named is None:
            return Ok(data=None)
        at = int(named[1])
        found = await self._query(tenant, logs_query(tenant, None), at, at + 1, MOST_SAME_INSTANT)
        if isinstance(found, Unavailable):
            return found
        asked = [_record(time, line, labels, line_too=True) for time, line, labels in found]
        return Ok(data=next((each for each in asked if each.id == record_id), None))


def _digest(time_ns: int, line: str, labels: dict[str, str]) -> str:
    stream = "\x1f".join(f"{name}={labels[name]}" for name in sorted(labels))
    return hashlib.sha256(f"{time_ns}\x1e{stream}\x1e{line}".encode()).hexdigest()[:16]


def _record(
    time_ns: int, line: str, labels: dict[str, str], *, line_too: bool = False
) -> LogRecord:
    """A record as a read shows it: its safe labels, the names of the rest, its line's length.

    The one asked for has its line too.
    """
    safe = {name: value for name, value in labels.items() if name in SAFE_LABELS}
    return LogRecord(
        id=f"{time_ns}-{_digest(time_ns, line, labels)}",
        time_ns=time_ns,
        level=labels.get("detected_level") or (labels.get("severity_text") or "").lower() or None,
        service=safe.get("service_name"),
        thread=safe.get(THREAD_METADATA),
        run=safe.get("artifactr_run_id") or safe.get("reflexr_run_id"),
        length=len(line),
        labels=safe,
        withheld=tuple(sorted(set(labels) - SAFE_LABELS)),
        line=line if line_too else None,
    )
