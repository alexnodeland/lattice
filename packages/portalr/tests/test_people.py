"""Supabase Auth's users, read for their emails: kept briefly, bounded, and never in an error."""

import asyncio
from collections.abc import Mapping
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

    def __init__(self, emails: Mapping[str, str | None]) -> None:
        self.emails = dict(emails)
        self.requests: list[httpx.Request] = []
        self.script: dict[str, httpx.Response | Exception] = {}
        self.running = 0
        self.most = 0
        self.pause = 0.0
        self.hold: set[str] = set()
        self.release = asyncio.Event()
        self._held = asyncio.Condition()

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        id = request.url.path.removeprefix(USERS)
        self.running += 1
        self.most = max(self.most, self.running)
        try:
            if self.pause:
                await asyncio.sleep(self.pause)
            if id in self.hold:
                async with self._held:
                    self._held.notify_all()
                await self.release.wait()
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

    async def held_at(self, running: int) -> None:
        """Wait until ``running`` reads are under way and held."""
        async with self._held:
            await self._held.wait_for(lambda: self.running >= running)

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


async def test_a_failed_read_is_left_alone_for_a_few_seconds_and_then_read_again() -> None:
    clock = Clock()
    auth = Auth({"u1": "ada@acme.com"})
    auth.script["u1"] = httpx.ConnectError("down")
    people = auth.people(clock, failed_for=5)
    assert await people(["u1"]) == {}
    del auth.script["u1"]
    assert await people(["u1"]) == {}, "not asked again at once"
    assert auth.asked == ["u1"]
    clock.now += 6
    assert await people(["u1"]) == {"u1": "ada@acme.com"}


@pytest.mark.parametrize("status", [401, 403, 429, 500, 502, 503])
async def test_a_limited_or_failing_supabase_is_not_asked_again_by_every_request(
    status: int,
) -> None:
    clock = Clock()
    auth = Auth({"u1": "ada@acme.com"})
    auth.script["u1"] = httpx.Response(status, json={})
    people = auth.people(clock, failed_for=5)
    for _ in range(3):
        assert await people(["u1"]) == {}
    assert auth.asked == ["u1"], "one read for three requests"
    clock.now += 6
    del auth.script["u1"]
    assert await people(["u1"]) == {"u1": "ada@acme.com"}


async def test_retry_after_is_honoured_within_a_minute() -> None:
    clock = Clock()
    auth = Auth({"u1": "ada@acme.com", "u2": "bo@acme.com", "u3": "cy@acme.com"})
    auth.script["u1"] = httpx.Response(429, headers={"retry-after": "30"}, json={})
    auth.script["u2"] = httpx.Response(429, headers={"retry-after": "9999"}, json={})
    auth.script["u3"] = httpx.Response(429, headers={"retry-after": "soon"}, json={})
    people = auth.people(clock, failed_for=5)
    await people(["u1", "u2", "u3"])
    for scripted in ("u1", "u2", "u3"):
        del auth.script[scripted]
    clock.now += 6
    assert await people(["u1", "u2", "u3"]) == {"u3": "cy@acme.com"}, "u3 had no usable header"
    clock.now += 25
    assert await people(["u1", "u2", "u3"]) == {"u1": "ada@acme.com", "u3": "cy@acme.com"}
    clock.now += 31
    assert set(await people(["u1", "u2", "u3"])) == {"u1", "u2", "u3"}, "a minute at most"


async def test_an_id_is_matched_without_regard_to_case() -> None:
    auth = Auth({})
    auth.script["abc-def"] = httpx.Response(200, json={"id": "ABC-DEF", "email": "ada@acme.com"})
    assert await auth.people()(["abc-def"]) == {"abc-def": "ada@acme.com"}


async def test_calls_for_the_same_id_at_once_share_one_read() -> None:
    auth = Auth({"u1": "ada@acme.com"})
    auth.pause = 0.05
    people = auth.people()
    first, second = await asyncio.gather(people(["u1"]), people(["u1"]))
    assert first == second == {"u1": "ada@acme.com"}
    assert auth.asked == ["u1"]


async def test_one_big_call_leaves_the_rest_of_the_reads_to_others() -> None:
    auth = Auth({f"u{i}": f"u{i}@x.io" for i in range(30)} | {"small": "small@x.io"})
    auth.hold = {f"u{i}" for i in range(30)}
    people = auth.people(concurrency=8, per_call=4)
    big = asyncio.create_task(people([f"u{i}" for i in range(30)]))
    await auth.held_at(4)
    # The big call's reads are held, so the small call is answered only from a free share.
    # A bound on a call that should not wait at all, so a regression fails here, not by hanging.
    async with asyncio.timeout(10):
        small = await people(["small"])
    assert small == {"small": "small@x.io"}, "and the next call is not kept waiting"
    assert auth.running == 4, "a call uses its share of the reads, not all"
    assert not big.done()
    auth.release.set()
    assert len(await big) == 30
    assert auth.most <= 8


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


async def test_all_the_reads_together_are_cut_off_at_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The loop's clock, which the deadline is timed by, moves only when the test moves it: u0 is
    # read, u1 is held, and then the deadline passes, however busy the machine is (#801).
    loop = asyncio.get_running_loop()
    clock = Clock()
    monkeypatch.setattr(loop, "time", clock)
    auth = Auth({f"u{i}": f"u{i}@x.io" for i in range(6)})
    auth.hold = {f"u{i}" for i in range(1, 6)}
    people = auth.people(concurrency=1, each=5, deadline=1)
    call = asyncio.create_task(people([f"u{i}" for i in range(6)]))
    await auth.held_at(1)
    clock.now += 2
    found = await call
    auth.release.set()
    await asyncio.gather(*people._reading.values())
    assert found == {"u0": "u0@x.io"}, "what was read in time is answered, the rest left out"


async def test_a_failed_read_is_an_absence_not_an_exception() -> None:
    auth = Auth({"u1": "ada@acme.com"})
    auth.script["u1"] = httpx.ConnectError("down ada@acme.com")
    assert await auth.people()(["u1"]) == {}


def test_the_secret_key_is_not_in_its_repr() -> None:
    assert "sb_secret_key" not in repr(
        SupabasePeople(url="http://auth", secret_key="sb_secret_key")
    )
