"""Umami, a second consumer of the relay's events, for operators' journeys (stackr ADR-0050).

And a deep link to its website, every tenant's journeys, for operators alone.

ClickHouse stays the record (lattice RFC-0008). The relay sends Umami a copy of each consented
event, from portalr's own address: no person's network address, browser or user agent reaches
it, only a fixed agent of portalr's. A person is ``<tenant's tag>:<keyed hash>``, Umami's
distinct id, so each person has a session of their own in each tenant, and a deletion can find
them: all of
their sessions when they say no, or one tenant's when they are removed from it (portalr ADR-0076).

Umami's ingest takes anyone's events, so it is reachable only on a network stackr shares with the
application alone. Its deletions are portalr's user's, who owns the website.
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Final, cast

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

VISIT_MINUTES: Final = 10
"""How long a visit's token is used for a person's replay batches before the visit is sent again."""

MOST_VISITS: Final = 10_000
"""How many people's visit tokens are remembered."""

ASK: Final = 1.0
"""How long a question to Umami about its replay may take, in seconds: config.json waits on it."""

REPLAY_SECONDS: Final = 60.0
"""How long Umami's answer to whether its website keeps replays is believed."""

PAGE: Final = 100
"""How many sessions one page of a search reads."""

MOST_ROUNDS: Final = 10
"""How many times a deletion searches again before it says it wasn't done: each round deletes
every session of the person's that the search found, page by page."""


DISTINCT_LENGTH: Final = 50
"""The longest distinct id Umami keeps: a longer one is cut, and found by no exact match."""


def tenant_tag(tenant: str) -> str:
    """A tenant as Umami knows it: 16 hex digits of its id's hash, whatever its id's length."""
    return hashlib.sha256(tenant.encode()).hexdigest()[:16]


def distinct(tenant: str, person: str) -> str:
    """A person in a tenant, as Umami's distinct id: the tenant's tag and their keyed hash.

    49 characters, under Umami's ``DISTINCT_LENGTH``, whatever the tenant's id.
    """
    return f"{tenant_tag(tenant)}:{person}"


@dataclass
class _Rest:
    """Until when the copies rest, after Umami failed one: a short circuit-breaker."""

    until: float = 0.0
    replay: tuple[float, bool] = (0.0, False)
    """When Umami was last asked whether its website keeps replays, and what it answered."""
    asking: asyncio.Lock = field(default_factory=asyncio.Lock)
    """One question to Umami about its replay at a time: the rest wait, then read its answer."""
    visits: dict[str, tuple[float, str]] = field(default_factory=dict[str, tuple[float, str]])
    """The token Umami gave a person's visit, by distinct id, and when: a replay's batches in a
    session send the visit once."""


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
                    "id": distinct(tenant, person),
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

    async def replay_enabled(self) -> bool:
        """Whether Umami's website keeps replays, as portalr's user reads it; false if unsure.

        The answer is believed for a minute. Umami says in a 200 that a website's replay is off,
        so without this a batch would be reported as recorded that nothing keeps.
        """
        if time.monotonic() < self._rest.replay[0]:
            return self._rest.replay[1]
        async with self._rest.asking:
            at, known = self._rest.replay
            now = time.monotonic()
            if now < at:
                return known
            try:
                known = await asyncio.wait_for(self._replay_kept(), ASK)
                self._rest.replay = (now + REPLAY_SECONDS, known)
            except Exception as error:  # Umami's failure is never the request's.
                log.warning("analytics: Umami wasn't asked about replay: %s", type(error).__name__)
                self._rest.replay = (now + REST, False)
                return False
            return known

    async def _replay_kept(self) -> bool:
        """What Umami says of its website: whether it records, and whether it keeps replays."""
        headers = await self._signed_in()
        response = await self.client.get(
            f"{self.url}/api/websites/{self.website}", headers=headers, timeout=TIMEOUT
        )
        response.raise_for_status()
        body = cast("dict[str, Any]", response.json())
        config = body.get("replayConfig")
        return (
            body.get("recorderEnabled") is True
            and isinstance(config, dict)
            and cast("dict[str, Any]", config).get("replayEnabled") is True
        )

    async def record(self, tenant: str, person: str, events: list[dict[str, Any]]) -> bool:
        """Send a person's replay events: whether Umami kept them (portalr ADR-0077).

        Umami keeps a replay in the session a send names, by the token its answer carries: so a
        send of the person's visit, once for ten minutes of batches, then the events, with that
        token. Umami says, in a 200, where its website's replay is off; that is no replay kept.
        Any failure is caught and said.
        """
        if time.monotonic() < self._rest.until:
            return False
        who = distinct(tenant, person)
        try:
            token = await self._visit(who)
            kept = await self.client.post(
                f"{self.url}/api/record",
                json={"type": "record", "payload": {"website": self.website, "events": events}},
                headers={"User-Agent": AGENT, "x-umami-cache": token},
                timeout=TIMEOUT,
            )
            kept.raise_for_status()
            if kept.json().get("ok") is not True:
                self._rest.visits.pop(who, None)
                log.warning("analytics: Umami kept no replay: %s", kept.json().get("reason"))
                return False
        except Exception as error:  # Umami's failure is never the request's.
            self._rest.visits.pop(who, None)
            self._rest.until = time.monotonic() + REST
            log.warning("analytics: Umami didn't take a replay: %s", type(error).__name__)
            return False
        return True

    async def _visit(self, who: str) -> str:
        """The token of a person's visit, sent if it isn't already a recent one's."""
        now = time.monotonic()
        known = self._rest.visits.get(who)
        if known is not None and now < known[0]:
            return known[1]
        visit = await self.client.post(
            f"{self.url}/api/send",
            json={
                "type": "event",
                "payload": {
                    "website": self.website,
                    "hostname": HOSTNAME,
                    "url": "/",
                    "name": "app.replay.recorded.v1",
                    "id": who,
                },
            },
            headers={"User-Agent": AGENT},
            timeout=TIMEOUT,
        )
        visit.raise_for_status()
        token = str(visit.json()["cache"])
        if len(self._rest.visits) >= MOST_VISITS:
            self._rest.visits.clear()
        self._rest.visits[who] = (now + VISIT_MINUTES * 60, token)
        return token

    async def forget(self, person: str, tenant: str | None = None) -> bool:
        """Delete a person's sessions, and their events, in one tenant or in all: whether done.

        portalr's user signs in, and searches for the person's hash: every page of the answer,
        each session read to check its distinct id is theirs exactly, then each deleted. It
        searches again until a round finds none of theirs; one still finding some after
        ``MOST_ROUNDS`` isn't done.
        """
        for who in [who for who in self._rest.visits if who.endswith(f":{person}")]:
            if tenant is None or who.startswith(f"{tenant_tag(tenant)}:"):
                del self._rest.visits[who]
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
                if whose == person and (tenant is None or owner == tenant_tag(tenant)):
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
