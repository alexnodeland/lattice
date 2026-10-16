"""Naming people: the email of a user id, which grantr does not hold.

grantr knows a person by their Supabase Auth user id, a UUID, and holds nothing else about them.
portalr's router asks this hook for the emails of ids it has already checked the caller may see
(portalr ADR-0034). An email is personal data, so nothing here logs one, puts one in an error, or
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


@dataclass(eq=False)
class SupabasePeople:
    """Supabase Auth's admin API, one user at a time, behind a short cache.

    Each id is read with ``GET /auth/v1/admin/users/{id}``, at most ``concurrency`` at a time,
    each within ``each`` seconds and all within ``deadline``. An email is kept ``found_for``
    seconds, an id that has none or no user ``missing_for``, in memory, and at most ``size``
    ids are held. A read that fails or times out is not kept, and its id is left out.

    Args:
        url: The Supabase project's URL.
        secret_key: The project's secret (service role) key.
        client: The HTTP client to send requests with.
        found_for: Seconds an email is kept.
        missing_for: Seconds an id without an email, or without a user, is kept.
        size: How many ids the cache holds before it drops the oldest.
        concurrency: How many users are read at once.
        each: Seconds one read may take.
        deadline: Seconds all of a call's reads may take together.
        clock: Returns the time in seconds, for the cache.
    """

    url: str
    secret_key: str
    client: httpx.AsyncClient = field(default_factory=httpx.AsyncClient)
    found_for: float = 300.0
    missing_for: float = 60.0
    size: int = 2048
    concurrency: int = 8
    each: float = 3.0
    deadline: float = 8.0
    clock: Callable[[], float] = time.monotonic
    _kept: dict[str, tuple[float, str | None]] = field(init=False)
    _slots: asyncio.Semaphore = field(init=False)

    def __post_init__(self) -> None:
        self._kept = {}
        self._slots = asyncio.Semaphore(self.concurrency)

    async def __call__(self, ids: Collection[str]) -> dict[str, str]:
        """The email of each id that has one; the others are left out."""
        wanted = list(dict.fromkeys(ids))
        unknown = [each for each in wanted if self._recall(each) is _UNKNOWN]
        if unknown:
            try:
                async with asyncio.timeout(self.deadline):
                    await asyncio.gather(*(self._read(each) for each in unknown))
            except TimeoutError:
                pass  # what was read in time is kept; the rest is left out
        found: dict[str, str] = {}
        for each in wanted:
            email = self._recall(each)
            if isinstance(email, str):
                found[each] = email
        return found

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
                return
        if response.status_code == 404:
            self._keep(user, None, self.missing_for)
            return
        if response.status_code != 200:
            return
        try:
            found = _USER.validate_json(response.content)
        except ValidationError:
            return
        if found.id == user:
            self._keep(
                user, found.email or None, self.found_for if found.email else self.missing_for
            )
