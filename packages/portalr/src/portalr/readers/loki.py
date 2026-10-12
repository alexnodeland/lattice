"""Loki: a tenant's logs, read with LogQL and filtered by tenant.

Every query filters on the ``tenant_id`` structured metadata, where Loki keeps the collector's
``tenant.id``.
"""

from dataclasses import dataclass, field
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter

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


class LogQuery(Window):
    """Which of a tenant's logs to read: a thread's, a run's, or any, in a window."""

    thread: Id | None = None
    run: Id | None = None


class LogLine(BaseModel):
    """One log record."""

    model_config = ConfigDict(frozen=True)

    time_ns: int
    line: str
    labels: dict[str, str]


class _Stream(BaseModel):
    stream: dict[str, str]
    values: list[tuple[str, str] | tuple[str, str, dict[str, str]]]


class _Data(BaseModel):
    result: list[_Stream] = []


class _Answer(BaseModel):
    data: _Data


_ANSWER: Final = TypeAdapter(_Answer)


def logs_query(tenant: Tenant, query: LogQuery) -> str:
    """The LogQL that reads a tenant's logs: always ``tenant_id``, then the filters."""
    stages = [f"{TENANT_METADATA} = {quoted(tenant.id)}"]
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

    async def logs(self, tenant: Tenant, query: LogQuery) -> Ok[list[LogLine]] | Unavailable:
        """The tenant's log records that match the query, newest first."""
        answer = await read(
            self.client,
            "loki",
            f"{self.url}/loki/api/v1/query_range",
            _ANSWER,
            params={
                "query": logs_query(tenant, query),
                "start": int(query.start.timestamp() * 1_000_000_000),
                "end": int(query.end.timestamp() * 1_000_000_000),
                "limit": query.limit,
                "direction": "backward",
            },
        )
        if answer is None or isinstance(answer, Unavailable):
            return answer or Unavailable(reason="loki has no query API at that address")
        lines = [
            LogLine(time_ns=int(value[0]), line=value[1], labels=stream.stream)
            for stream in answer.data.result
            for value in stream.values
        ]
        return Ok(data=sorted(lines, key=lambda line: line.time_ns, reverse=True)[: query.limit])
