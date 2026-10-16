"""Naming people: the email of a user id, which grantr does not hold.

grantr knows a person by their Supabase Auth user id, a UUID, and holds nothing else about them.
portalr's router asks this hook for the emails of ids it has already checked the caller may see
(portalr ADR-0036). An email is personal data, so nothing here logs one, puts one in an error, or
keeps one beyond a short, bounded, in-memory cache. An id that can't be resolved is left out of
the answer, and the UIs show a short id for it.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Collection, Mapping
from dataclasses import dataclass, field
from typing import Final
from urllib.parse import quote

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

People = Callable[[Collection[str]], Awaitable[Mapping[str, str]]]
"""Returns the email of each user id it can resolve; the ids it can't are left out. It never
raises for an id it can't resolve, and never puts an email in an error."""


class _User(BaseModel):
    id: str
    email: str | None = None


_USER: Final = TypeAdapter(_User)

_UNKNOWN: Final = object()
"""What the cache answers for an id it does not hold."""

_MOST_RETRY_AFTER: Final = 60.0
"""The longest a ``Retry-After`` keeps an id from being read again, in seconds."""


@dataclass(eq=False)
class SupabasePeople:
    """Supabase Auth's admin API, one user at a time, behind a short cache.

    Each id is read with ``GET /auth/v1/admin/users/{id}``. At most ``concurrency`` reads run at
    once, and one call uses at most ``per_call`` of them, so a call for many ids leaves the rest
    to others. Each read takes at most ``each`` seconds, and all of a call's within ``deadline``.
    Concurrent calls for an id share one read.

    An email is kept ``found_for`` seconds, an id that has none or no user ``missing_for``, and
    an id whose read failed, Supabase being down, slow or limiting, ``failed_for`` (or what its
    ``Retry-After`` says, within a minute), so a failing Supabase is not asked again by every
    request. At most ``size`` ids are held, in memory; the oldest kept goes first.

    Args:
        url: The Supabase project's URL.
        secret_key: The project's secret (service role) key.
        client: The HTTP client to send requests with.
        found_for: Seconds an email is kept.
        missing_for: Seconds an id without an email, or without a user, is kept.
        failed_for: Seconds an id whose read failed is left alone.
        size: How many ids the cache holds before it drops the oldest kept.
        concurrency: How many users are read at once, in all.
        per_call: How many of them one call may use.
        each: Seconds one read may take.
        deadline: Seconds all of a call's reads may take together.
        clock: Returns the time in seconds, for the cache.
    """

    url: str
    secret_key: str
    client: httpx.AsyncClient = field(default_factory=httpx.AsyncClient)
    found_for: float = 300.0
    missing_for: float = 60.0
    failed_for: float = 5.0
    size: int = 2048
    concurrency: int = 8
    per_call: int = 4
    each: float = 3.0
    deadline: float = 8.0
    clock: Callable[[], float] = time.monotonic
    _kept: dict[str, tuple[float, str | None]] = field(init=False)
    _slots: asyncio.Semaphore = field(init=False)
    _reading: dict[str, asyncio.Task[None]] = field(init=False)

    def __post_init__(self) -> None:
        self._kept = {}
        self._slots = asyncio.Semaphore(self.concurrency)
        self._reading = {}

    async def __call__(self, ids: Collection[str]) -> dict[str, str]:
        """The email of each id that has one; the others are left out."""
        wanted = list(dict.fromkeys(ids))
        unknown = [each for each in wanted if self._recall(each) is _UNKNOWN]
        if unknown:
            await self._fetch(unknown)
        found: dict[str, str] = {}
        for each in wanted:
            email = self._recall(each)
            if isinstance(email, str):
                found[each] = email
        return found

    async def _fetch(self, unknown: list[str]) -> None:
        """Read the ids nobody is reading, and wait for them all, within the deadline."""
        share = asyncio.Semaphore(self.per_call)

        async def one(user: str) -> None:
            async with share:
                # Shielded: a call that stops waiting leaves the read to finish for the others.
                await asyncio.shield(self._read_once(user))

        waits = [asyncio.ensure_future(one(each)) for each in unknown]
        _, late = await asyncio.wait(waits, timeout=self.deadline)
        for wait in late:
            wait.cancel()

    def _read_once(self, user: str) -> asyncio.Task[None]:
        """The read of an id that is under way, or a new one."""
        reading = self._reading.get(user)
        if reading is None:
            reading = asyncio.ensure_future(self._read(user))
            self._reading[user] = reading
            reading.add_done_callback(lambda _done: self._reading.pop(user, None))
        return reading

    def _recall(self, user: str) -> object:
        kept = self._kept.get(user)
        if kept is None or kept[0] <= self.clock():
            return _UNKNOWN
        return kept[1]

    def _keep(self, user: str, email: str | None, seconds: float) -> None:
        if user not in self._kept and len(self._kept) >= self.size:
            now = self.clock()
            for old in [each for each, (until, _) in self._kept.items() if until <= now]:
                del self._kept[old]
            if len(self._kept) >= self.size:
                del self._kept[next(iter(self._kept))]
        self._kept[user] = (self.clock() + seconds, email)

    async def _read(self, user: str) -> None:
        headers = {"apikey": self.secret_key, "Authorization": f"Bearer {self.secret_key}"}
        async with self._slots:
            try:
                async with asyncio.timeout(self.each):
                    response = await self.client.get(
                        f"{self.url}/auth/v1/admin/users/{quote(user, safe='')}", headers=headers
                    )
            except (httpx.HTTPError, TimeoutError):
                self._keep(user, None, self.failed_for)
                return
        if response.status_code == 404:
            self._keep(user, None, self.missing_for)
        elif response.status_code == 200:
            self._found(user, response)
        else:
            # Limited, failing, or refusing our key: left alone for a few seconds, not asked again
            # by every request.
            self._keep(user, None, self._wait(response))

    def _wait(self, response: httpx.Response) -> float:
        """How long to leave an id alone after Supabase failed or limited the read."""
        try:
            asked = float(response.headers.get("retry-after", ""))
        except ValueError:
            return self.failed_for
        return min(max(asked, self.failed_for), _MOST_RETRY_AFTER)

    def _found(self, user: str, response: httpx.Response) -> None:
        try:
            found = _USER.validate_json(response.content)
        except ValidationError:
            self._keep(user, None, self.failed_for)
            return
        if found.id.casefold() == user.casefold():
            seconds = self.found_for if found.email else self.missing_for
            self._keep(user, found.email or None, seconds)
