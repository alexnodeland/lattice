"""Supabase Auth's users, read for their emails: kept briefly, bounded, and never in an error."""

import asyncio
from typing import Any

import httpx
import pytest

from portalr.people import SupabasePeople

USERS = "/auth/v1/admin/users/"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Auth:
    """Supabase Auth's admin users: an email by id, or none, or a script for a read."""

    def __init__(self, emails: dict[str, str | None]) -> None:
        self.emails = emails
        self.requests: list[httpx.Request] = []
        self.script: dict[str, httpx.Response | Exception] = {}
        self.running = 0
        self.most = 0
        self.pause = 0.0

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        id = request.url.path.removeprefix(USERS)
        self.running += 1
        self.most = max(self.most, self.running)
        try:
            if self.pause:
                await asyncio.sleep(self.pause)
        finally:
            self.running -= 1
        scripted = self.script.get(id)
        if isinstance(scripted, Exception):
            raise scripted
        if scripted is not None:
            return scripted
        if id not in self.emails:
            return httpx.Response(404, json={"msg": "User not found"})
        return httpx.Response(200, json={"id": id, "email": self.emails[id]})

    def people(self, clock: Clock | None = None, **options: Any) -> SupabasePeople:
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.handle))
        return SupabasePeople(
            "https://project.supabase.co", "sb_secret_x", client, clock=clock or Clock(), **options
        )

    @property
    def asked(self) -> list[str]:
        return [request.url.path.removeprefix(USERS) for request in self.requests]


async def test_each_id_is_read_with_the_secret_key_and_answered_with_its_email() -> None:
    auth = Auth({"u1": "ada@acme.com", "u2": "bo@acme.com"})
    assert await auth.people()(["u1", "u2", "u1"]) == {"u1": "ada@acme.com", "u2": "bo@acme.com"}
    assert sorted(auth.asked) == ["u1", "u2"], "each once"
    request = auth.requests[0]
    assert request.headers["apikey"] == "sb_secret_x"
    assert request.headers["authorization"] == "Bearer sb_secret_x"
    assert request.url.host == "project.supabase.co"


async def test_an_id_is_quoted_in_the_path() -> None:
    auth = Auth({})
    await auth.people()(["a/b?c"])
    assert auth.requests[0].url.raw_path.decode() == "/auth/v1/admin/users/a%2Fb%3Fc"


@pytest.mark.parametrize(
    ("emails", "script"),
    [
        pytest.param({}, {}, id="no user"),
        pytest.param({"u1": None}, {}, id="a user without an email"),
        pytest.param({"u1": ""}, {}, id="an empty email"),
        pytest.param({}, {"u1": httpx.Response(500, json={})}, id="a failing read"),
        pytest.param({}, {"u1": httpx.Response(200, text="not json")}, id="an unreadable answer"),
        pytest.param(
            {}, {"u1": httpx.Response(200, json={"id": "other", "email": "x@y.z"})}, id="another id"
        ),
        pytest.param({}, {"u1": httpx.ConnectError("down")}, id="a service that is down"),
    ],
)
async def test_an_id_it_cannot_resolve_is_left_out(
    emails: dict[str, str | None], script: dict[str, httpx.Response | Exception]
) -> None:
    auth = Auth(emails)
    auth.script = script
    assert await auth.people()(["u1"]) == {}


async def test_emails_are_kept_for_a_while_and_read_again_after() -> None:
    clock = Clock()
    auth = Auth({"u1": "ada@acme.com"})
    people = auth.people(clock, found_for=300, missing_for=60)
    assert await people(["u1", "nobody"]) == {"u1": "ada@acme.com"}
    assert await people(["u1", "nobody"]) == {"u1": "ada@acme.com"}
    assert sorted(auth.asked) == ["nobody", "u1"], "the second call read nothing"
    clock.now += 61
    await people(["u1", "nobody"])
    assert auth.asked[2:] == ["nobody"], "a missing user is read again first"
    clock.now += 300
    auth.emails["u1"] = "ada@new.com"
    assert await people(["u1"]) == {"u1": "ada@new.com"}


async def test_a_failed_read_is_not_kept() -> None:
    auth = Auth({"u1": "ada@acme.com"})
    auth.script["u1"] = httpx.ConnectError("down")
    people = auth.people()
    assert await people(["u1"]) == {}
    del auth.script["u1"]
    assert await people(["u1"]) == {"u1": "ada@acme.com"}


async def test_the_cache_holds_at_most_its_size_and_drops_the_oldest() -> None:
    clock = Clock()
    auth = Auth({"a": "a@x.io", "b": "b@x.io", "c": "c@x.io"})
    people = auth.people(clock, size=2, found_for=100)
    await people(["a"])
    await people(["b"])
    await people(["c"])
    assert len(people._kept) == 2
    assert "a" not in people._kept, "the oldest went"
    clock.now += 101
    await people(["a"])
    assert set(people._kept) == {"a"}, "expired entries go first"


async def test_reads_are_limited_in_number_and_time() -> None:
    auth = Auth({f"u{i}": f"u{i}@x.io" for i in range(20)})
    auth.pause = 0.01
    found = await auth.people(concurrency=3)([f"u{i}" for i in range(20)])
    assert len(found) == 20
    assert auth.most <= 3, "at most three at once"


async def test_a_slow_read_is_cut_off_and_the_rest_are_answered() -> None:
    auth = Auth({"slow": "slow@x.io", "fast": "fast@x.io"})
    original = auth.handle

    async def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("slow"):
            await asyncio.sleep(1)
        return await original(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    people = SupabasePeople("https://p.supabase.co", "k", client, each=0.05, deadline=5)
    assert await people(["slow", "fast"]) == {"fast": "fast@x.io"}


async def test_all_the_reads_together_are_cut_off_at_the_deadline() -> None:
    auth = Auth({f"u{i}": f"u{i}@x.io" for i in range(6)})
    auth.pause = 0.2
    people = auth.people(concurrency=1, each=5, deadline=0.35)
    found = await people([f"u{i}" for i in range(6)])
    assert 1 <= len(found) < 6, "what was read in time is answered, the rest left out"
    assert set(found) <= set(auth.emails)


async def test_an_email_is_in_no_error_the_hook_raises() -> None:
    auth = Auth({"u1": "ada@acme.com"})
    auth.script["u1"] = httpx.ConnectError("down ada@acme.com")
    assert await auth.people()(["u1"]) == {}, "a failure is an absence, not an exception"
