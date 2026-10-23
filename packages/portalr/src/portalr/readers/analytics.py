"""portalr's product analytics on ClickHouse (lattice RFC-0008): written, and read per tenant.

Events go to ``analytics.events`` as ClickHouse's ``portalr_analytics_writer``, which may insert
there and nothing else. Each is named in the registry, ``analytics_events.json``, and carries only
the keys the registry allows; its tenant and workspace are the server's, never a browser's; and
the person is a keyed hash of their id, ``distinct_id``, so analytics never holds the id itself.
A write that fails is logged and dropped: analytics never fails the action it records.

Reads are ClickHouse's ``portalr_analytics``'s, which may only read ``analytics.events``, and only
the rows of the tenant a query's ``SQL_portalr_tenant`` setting names (stackr ADR-0044). Every
query here names the tenant twice, in that setting and in its own ``WHERE``, each a parameter,
never text in the query: a reader that forgot one would still be held to the tenant by the other.
"""

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import resources
from typing import Final, Literal

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter

from grantr.core import ServicePrincipal, Subject, User
from portalr.readers.query import Span
from portalr.readers.reading import Ok, Unavailable
from portalr.tenant import Tenant

log = logging.getLogger("portalr.analytics")

REGISTRY: Final[dict[str, dict[str, frozenset[str] | None]]] = {
    name: {key: None if values == "route" else frozenset(values) for key, values in props.items()}
    for name, props in json.loads(
        resources.files("portalr.readers").joinpath("analytics_events.json").read_text()
    )["events"].items()
}
"""Each event portalr records, by its versioned name: each key it may carry, with the values it
may take, or None for a route, which the relay holds to the app's router's own."""

TENANT_SETTING: Final = "SQL_portalr_tenant"
"""The custom setting the row policy on ``analytics.events`` reads a query's tenant from."""

TIMEOUT: Final = 5.0
"""How long a write or a read may take, in seconds."""

Actor = Literal["user", "principal", "agent"]


def actor_of(subject: Subject) -> tuple[Actor, str] | None:
    """Who an event is by: a person or a service principal, by its id; None for anyone else."""
    if isinstance(subject, User):
        return "user", subject.id
    if isinstance(subject, ServicePrincipal):
        return "principal", subject.id
    return None


def distinct_id(key: bytes, user_id: str) -> str:
    """A person as analytics knows them: the deployment's keyed hash of their id, 32 hex digits."""
    return hmac.new(key, user_id.encode(), hashlib.sha256).hexdigest()[:32]


class EventCount(BaseModel):
    """How many times an event was recorded in a tenant, by how many people."""

    model_config = ConfigDict(frozen=True)

    event: str
    count: int
    people: int


_COUNTS = TypeAdapter(list[EventCount])


@dataclass(frozen=True)
class Analytics:
    """ClickHouse's ``analytics`` database, written by one user and read by another.

    Args:
        url: ClickHouse's HTTP interface, such as ``http://clickhouse:8123``.
        key: The deployment's key for hashing a person's id (``PORTAL_ANALYTICS_KEY``).
        writer: The client that inserts, with ``portalr_analytics_writer``'s basic auth.
        reader: The client that reads, with ``portalr_analytics``'s basic auth.
    """

    url: str
    key: bytes = field(repr=False)
    writer: httpx.AsyncClient = field(default_factory=httpx.AsyncClient)
    reader: httpx.AsyncClient = field(default_factory=httpx.AsyncClient)

    async def capture(
        self,
        tenant: str,
        event: str,
        user_id: str,
        *,
        actor: Actor = "user",
        workspace: str = "",
        trace_id: str = "",
        session_id: str = "",
        props: dict[str, str] | None = None,
    ) -> bool:
        """Record an event in the tenant: whether it was written.

        Raises:
            ValueError: If the event isn't in the registry: a name is the code's, not a person's.
        """
        row = self._row(tenant, event, user_id, actor, workspace, trace_id, session_id, props)
        return await self._write(
            "INSERT INTO analytics.events FORMAT JSONEachRow", json.dumps(row), event
        )

    async def capture_many(
        self,
        tenant: str,
        user_id: str,
        events: list[tuple[str, dict[str, str]]],
        *,
        session_id: str = "",
    ) -> bool:
        """Record a person's events in the tenant, each its name and props, in one write.

        Raises:
            ValueError: If an event isn't in the registry.
        """
        rows = [
            self._row(tenant, event, user_id, "user", "", "", session_id, props)
            for event, props in events
        ]
        body = "\n".join(json.dumps(row) for row in rows)
        return await self._write("INSERT INTO analytics.events FORMAT JSONEachRow", body, "events")

    def _row(
        self,
        tenant: str,
        event: str,
        user_id: str,
        actor: Actor,
        workspace: str,
        trace_id: str,
        session_id: str,
        props: dict[str, str] | None,
    ) -> dict[str, object]:
        allowed = REGISTRY.get(event)
        if allowed is None:
            raise ValueError(f"{event!r} isn't in portalr's analytics registry")
        return {
            "ts": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "tenant_id": tenant,
            "workspace_id": workspace,
            "distinct_id": distinct_id(self.key, user_id),
            "event": event,
            "trace_id": trace_id,
            "session_id": session_id,
            "actor_kind": actor,
            "props": {
                key: value
                for key, value in (props or {}).items()
                if key in allowed and ((values := allowed[key]) is None or value in values)
            },
        }

    async def forget(self, user_id: str) -> bool:
        """Delete every event of the person's, in every tenant, at once: whether it was done.

        A lightweight delete: the rows are hidden from every read as it returns, and removed from
        disk as ClickHouse merges the parts that hold them (lattice RFC-0008, P5).
        """
        return await self._write(
            "DELETE FROM analytics.events WHERE distinct_id = {person:FixedString(32)}",
            "",
            "a person's events",
            params={"param_person": distinct_id(self.key, user_id)},
        )

    async def _write(
        self, query: str, body: str, what: str, *, params: dict[str, str] | None = None
    ) -> bool:
        try:
            if params is None:
                response = await self.writer.post(
                    self.url, params={"query": query}, content=body, timeout=TIMEOUT
                )
            else:
                response = await self.writer.post(
                    self.url, params=params, content=query, timeout=TIMEOUT
                )
        except httpx.HTTPError as error:
            log.warning("analytics: %s not recorded: %s", what, type(error).__name__)
            return False
        if response.status_code >= 400:
            log.warning(
                "analytics: %s not recorded: ClickHouse answered %s", what, response.status_code
            )
            return False
        return True

    async def counts(self, tenant: Tenant, span: Span) -> Ok[list[EventCount]] | Unavailable:
        """Each event recorded in the tenant in the span: how many times, by how many people."""
        query = (
            "SELECT event, count() AS count, uniq(distinct_id) AS people FROM analytics.events"
            " WHERE tenant_id = {tenant:String}"
            " AND ts >= {start:DateTime64(3, 'UTC')} AND ts < {end:DateTime64(3, 'UTC')}"
            " GROUP BY event ORDER BY count DESC, event FORMAT JSONEachRow"
        )
        try:
            response = await self.reader.post(
                self.url,
                params={
                    TENANT_SETTING: tenant.id,
                    "param_tenant": tenant.id,
                    "param_start": _clickhouse_time(span.start),
                    "param_end": _clickhouse_time(span.end),
                },
                content=query,
                timeout=TIMEOUT,
            )
        except httpx.HTTPError as error:
            return Unavailable(reason=f"ClickHouse didn't answer: {type(error).__name__}")
        if response.status_code >= 400:
            return Unavailable(reason=f"ClickHouse answered {response.status_code}")
        rows = "[" + ",".join(response.text.splitlines()) + "]"
        return Ok(data=_COUNTS.validate_json(rows))


def _clickhouse_time(at: datetime) -> str:
    """A moment as ClickHouse reads a ``DateTime64(3, 'UTC')`` parameter."""
    return at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
