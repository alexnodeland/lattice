"""Umami, a second consumer of the relay's events, for operators' journeys (stackr ADR-0050).

And a deep link to its website, every tenant's journeys, for operators alone.

ClickHouse stays the record (lattice RFC-0008). The relay sends Umami a copy of each consented
event, from portalr's own address: no person's network address, browser or user agent reaches
it, only a fixed agent of portalr's. A person is ``<tenant>:<keyed hash>``, Umami's distinct id,
so each person has a session of their own in each tenant, and a deletion can find them: all of
their sessions when they say no, or one tenant's when they are removed from it (portalr ADR-0076).

Umami's ingest takes anyone's events, so it is reachable only on a network stackr shares with the
application alone. Its deletions are portalr's user's, who owns the website.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Final

import httpx
from pydantic import BaseModel, Field, TypeAdapter

log = logging.getLogger("portalr.analytics")

AGENT: Final = "portalr-relay"
"""The user agent every request to Umami carries, in place of any person's."""

HOSTNAME: Final = "portalr.internal"
"""The host each event is recorded on: the website's domain."""

TIMEOUT: Final = 5.0
"""How long a request to Umami may take, in seconds."""

MOST_SESSIONS: Final = 100
"""The most sessions one search reads: a person has one per tenant, each month."""


class _Session(BaseModel):
    id: str
    distinct_id: str | None = Field(default=None, alias="distinctId")


class _Sessions(BaseModel):
    data: list[_Session]


_SESSIONS: Final = TypeAdapter(_Sessions)
_SESSION: Final = TypeAdapter(_Session)


@dataclass(frozen=True)
class Umami:
    """Umami's website for portalr, sent to and deleted from.

    Args:
        url: Umami's address on the application's network, such as ``http://umami:3000``.
        website: The website's id, which stackr's ``umami-init`` makes.
        password: portalr's Umami user's password, which owns the website.
        client: The client every request goes through.
    """

    url: str
    website: str
    password: str = field(repr=False)
    client: httpx.AsyncClient = field(default_factory=httpx.AsyncClient)

    async def send(
        self, tenant: str, person: str, events: list[tuple[str, dict[str, str]]]
    ) -> bool:
        """Send a person's events, each its name and props: whether Umami took them all.

        A failure is logged and dropped, as a write to ClickHouse is: Umami is never the record.
        """
        for name, props in events:
            payload = {
                "website": self.website,
                "hostname": HOSTNAME,
                "url": props.get("route") or "/",
                "name": name,
                "id": f"{tenant}:{person}",
                "data": {key: value for key, value in props.items() if key != "route"},
            }
            try:
                response = await self.client.post(
                    f"{self.url}/api/send",
                    json={"type": "event", "payload": payload},
                    headers={"User-Agent": AGENT},
                    timeout=TIMEOUT,
                )
            except httpx.HTTPError as error:
                log.warning("analytics: Umami didn't take an event: %s", type(error).__name__)
                return False
            if response.status_code >= 400:
                log.warning("analytics: Umami answered %s to an event", response.status_code)
                return False
        return True

    async def forget(self, person: str, tenant: str | None = None) -> bool:
        """Delete a person's sessions, and their events, in one tenant or in all: whether done.

        portalr's user signs in, finds the sessions whose distinct id names the person, reads each
        to check its id is theirs exactly, and deletes it.
        """
        try:
            token = await self._sign_in()
            headers = {"Authorization": f"Bearer {token}", "User-Agent": AGENT}
            now = int(time.time() * 1000) + 60_000
            found = await self.client.get(
                f"{self.url}/api/websites/{self.website}/sessions",
                params={"startAt": 0, "endAt": now, "search": person, "pageSize": MOST_SESSIONS},
                headers=headers,
                timeout=TIMEOUT,
            )
            found.raise_for_status()
            for listed in _SESSIONS.validate_json(found.content).data:
                path = f"{self.url}/api/websites/{self.website}/sessions/{listed.id}"
                read = await self.client.get(path, headers=headers, timeout=TIMEOUT)
                read.raise_for_status()
                named = _SESSION.validate_json(read.content).distinct_id or ""
                owner, _, whose = named.partition(":")
                if whose != person or (tenant is not None and owner != tenant):
                    continue
                gone = await self.client.delete(path, headers=headers, timeout=TIMEOUT)
                if gone.status_code not in (200, 404):
                    gone.raise_for_status()
        except (httpx.HTTPError, ValueError) as error:
            log.warning(
                "analytics: Umami didn't delete a person's sessions: %s", type(error).__name__
            )
            return False
        return True

    async def _sign_in(self) -> str:
        response = await self.client.post(
            f"{self.url}/api/auth/login",
            json={"username": "portalr", "password": self.password},
            headers={"User-Agent": AGENT},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return str(response.json()["token"])


@dataclass(frozen=True)
class UmamiLinks:
    """Links into Umami's UI.

    Args:
        url: Umami, as operators' browsers reach it, such as ``http://localhost:3400``.
        website: portalr's website's id there.
    """

    url: str
    website: str

    def website_link(self) -> str:
        """The link to portalr's website in Umami: every tenant's journeys."""
        return f"{self.url.rstrip('/')}/websites/{self.website}"
