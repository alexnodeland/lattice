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

TIMEOUT: Final = 2.0
"""How long a request to Umami may take, in seconds: a copy waits on no one for long."""

REST: Final = 30.0
"""How long, in seconds, the copies wait after Umami failed one, before trying it again."""

PAGE: Final = 100
"""How many sessions one page of a search reads."""

MOST_ROUNDS: Final = 10
"""How many times a deletion searches again before it says it wasn't done: each round deletes
every session of the person's that the search found, page by page."""


class _Rest:
    """Until when the copies rest, after Umami failed one: a short circuit-breaker."""

    until: float = 0.0


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

    Every failure of Umami's is caught here, whatever it is, and said by its type alone: Umami
    never fails a request of portalr's.

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
    _rest: _Rest = field(default_factory=_Rest, repr=False, compare=False)

    async def send(
        self, tenant: str, person: str, events: list[tuple[str, dict[str, str]]]
    ) -> bool:
        """Send a person's events, each its name and props: whether Umami took them all.

        A failure is logged and dropped, as a write to ClickHouse is: Umami is never the record.
        An event Umami refuses (4xx) is dropped alone. A transport error or a 5xx stops the rest,
        and the copies rest for ``REST`` seconds, sending nothing, so an Umami that is down costs
        each request nothing; the journeys have a gap where it was.
        """
        if time.monotonic() < self._rest.until:
            return False
        taken = True
        try:
            for name, props in events:
                payload = {
                    "website": self.website,
                    "hostname": HOSTNAME,
                    "url": props.get("route") or "/",
                    "name": name,
                    "id": f"{tenant}:{person}",
                    "data": {key: value for key, value in props.items() if key != "route"},
                }
                response = await self.client.post(
                    f"{self.url}/api/send",
                    json={"type": "event", "payload": payload},
                    headers={"User-Agent": AGENT},
                    timeout=TIMEOUT,
                )
                if 400 <= response.status_code < 500:
                    # This event's, not Umami's: it is dropped, and the others go on.
                    log.warning("analytics: Umami refused an event: %s", response.status_code)
                    taken = False
                    continue
                response.raise_for_status()
        except Exception as error:  # Umami's failure is never the request's.
            self._rest.until = time.monotonic() + REST
            log.warning("analytics: Umami didn't take an event: %s", type(error).__name__)
            return False
        return taken

    async def forget(self, person: str, tenant: str | None = None) -> bool:
        """Delete a person's sessions, and their events, in one tenant or in all: whether done.

        portalr's user signs in, and searches for the person's hash: every page of the answer,
        each session read to check its distinct id is theirs exactly, then each deleted. It
        searches again until a round finds none of theirs; one still finding some after
        ``MOST_ROUNDS`` isn't done.
        """
        try:
            headers = await self._signed_in()
            for _ in range(MOST_ROUNDS):
                theirs = await self._theirs(person, tenant, headers)
                if not theirs:
                    return True
                for session in theirs:
                    gone = await self.client.delete(
                        f"{self.url}/api/websites/{self.website}/sessions/{session}",
                        headers=headers,
                        timeout=TIMEOUT,
                    )
                    if gone.status_code != 404:
                        gone.raise_for_status()
        except Exception as error:  # Umami's failure is never the request's.
            log.warning(
                "analytics: Umami didn't delete a person's sessions: %s", type(error).__name__
            )
            return False
        log.warning("analytics: Umami still has a person's sessions after %d rounds", MOST_ROUNDS)
        return False

    async def sessions(self, person: str, tenant: str | None = None) -> list[str]:
        """The ids of the person's sessions, in the tenant if named; Umami's failures are raised.

        For checks, as stackr's smoke test makes them.
        """
        return await self._theirs(person, tenant, await self._signed_in())

    async def _theirs(self, person: str, tenant: str | None, headers: dict[str, str]) -> list[str]:
        """The sessions a search for the person finds that are theirs, in the tenant if named."""
        now = int(time.time() * 1000) + 60_000
        theirs: list[str] = []
        page = 1
        while True:
            found = await self.client.get(
                f"{self.url}/api/websites/{self.website}/sessions",
                params={
                    "startAt": 0,
                    "endAt": now,
                    "search": person,
                    "page": page,
                    "pageSize": PAGE,
                },
                headers=headers,
                timeout=TIMEOUT,
            )
            found.raise_for_status()
            listed = _SESSIONS.validate_json(found.content).data
            for session in listed:
                read = await self.client.get(
                    f"{self.url}/api/websites/{self.website}/sessions/{session.id}",
                    headers=headers,
                    timeout=TIMEOUT,
                )
                read.raise_for_status()
                named = _SESSION.validate_json(read.content).distinct_id or ""
                owner, _, whose = named.rpartition(":")
                if whose == person and (tenant is None or owner == tenant):
                    theirs.append(session.id)
            if len(listed) < PAGE:
                return theirs
            page += 1

    async def _signed_in(self) -> dict[str, str]:
        """The headers of a request as portalr's user, signed in."""
        return {"Authorization": f"Bearer {await self._sign_in()}", "User-Agent": AGENT}

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
