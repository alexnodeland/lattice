"""Umami: a copy of consented events, from portalr's own agent, and a person's deletion there."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from grantr.grants import Grants
from portalr.analytics import InMemoryConsent, InMemoryRateLimiter, Relay, Umami
from portalr.analytics.relay import MOST_COPIES, Batch, Event
from portalr.invites import Invite
from portalr.readers import Analytics, Readers
from portalr.readers.analytics import distinct_id
from portalr.readers.umami import (
    AGENT,
    DISTINCT_LENGTH,
    MOST_ROUNDS,
    PAGE,
    distinct,
    tenant_tag,
)

from .conftest import app_for

KEY = b"the deployment's key"
WEBSITE = "446fed1e-11a4-4c5f-9b72-31e6d4cf882d"
ME = distinct_id(KEY, "alice")
ACME, GLOBEX = tenant_tag("acme"), tenant_tag("globex")
BATCH = Batch(session="s", events=[Event(event="app.page.viewed.v1", route="/t/$tenant")])


class Stand:
    """Umami, as a test scripts it: its sessions, by id and distinct id, and what it was sent."""

    def __init__(self) -> None:
        self.sent: list[httpx.Request] = []
        self.sessions = {"s1": f"{ACME}:{ME}", "s2": f"{GLOBEX}:{ME}", "s3": f"{ACME}:{ME}x"}
        self.down = False
        self.vanished: str | None = None
        """A session gone by the time it is deleted, as another replica's deletion leaves it."""
        self.stuck: str | None = None
        """A session Umami says it deleted, and keeps."""
        self.after_send: list[Callable[[], Awaitable[None]]] = []
        self.recorded: list[list[object]] = []
        self.replay_off = False
        self.slow = 0.0
        """How long Umami takes to say whether its website keeps replays, in seconds."""
        self.refused: set[str] = set()
        """The events' names Umami refuses, as a 400."""
        self.sends_taken: int | None = None
        """How many sends Umami takes before it answers 503; every one, if None."""
        self.after_delete: list[Callable[[], None]] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        if self.down:
            return httpx.Response(503)
        path = request.url.path
        if path == "/api/auth/login":
            assert json.loads(request.content) == {"username": "portalr", "password": "pw"}
            return httpx.Response(200, json={"token": "t0k"})
        if path == "/api/record":
            assert request.headers["x-umami-cache"] == "c"
            self.recorded.append(json.loads(request.content)["payload"]["events"])
            if self.replay_off:
                return httpx.Response(200, json={"ok": False, "reason": "replay_disabled"})
            return httpx.Response(200, json={"ok": True})
        if path == f"/api/websites/{WEBSITE}" and request.method == "GET":
            await asyncio.sleep(self.slow)
            replay = {} if self.replay_off else {"replayEnabled": True}
            return httpx.Response(200, json={"recorderEnabled": True, "replayConfig": replay})
        if path == "/api/send":
            if json.loads(request.content)["payload"]["name"] in self.refused:
                return httpx.Response(400)
            if self.sends_taken is not None:
                if self.sends_taken == 0:
                    return httpx.Response(503)
                self.sends_taken -= 1
            for hook in self.after_send:
                await hook()
            return httpx.Response(200, json={"cache": "c"})
        if path == f"/api/websites/{WEBSITE}/sessions":
            assert request.headers["authorization"] == "Bearer t0k"
            params = request.url.params
            found = sorted(i for i, d in self.sessions.items() if params["search"] in d)
            page, size = int(params["page"]), int(params["pageSize"])
            return httpx.Response(
                200, json={"data": [{"id": i} for i in found[(page - 1) * size : page * size]]}
            )
        session = path.rsplit("/", 1)[1]
        if request.method == "DELETE":
            if session == self.vanished:
                self.sessions.pop(session)
                return httpx.Response(404)
            if session != self.stuck:
                self.sessions.pop(session)
            for hook in self.after_delete:
                hook()
            return httpx.Response(200)
        return httpx.Response(200, json={"id": session, "distinctId": self.sessions[session]})


@pytest.fixture
def stand() -> Stand:
    return Stand()


def umami_of(stand: Stand) -> Umami:
    return Umami(
        "http://umami:3000", WEBSITE, "pw", httpx.AsyncClient(transport=httpx.MockTransport(stand))
    )


async def test_each_event_goes_as_the_tenants_person(stand: Stand) -> None:
    assert await umami_of(stand).send(
        "acme", ME, [("app.page.viewed.v1", {"route": "/t/$tenant", "kind": "note"})]
    )
    (request,) = stand.sent
    assert json.loads(request.content) == {
        "type": "event",
        "payload": {
            "website": WEBSITE,
            "hostname": "portalr.internal",
            "url": "/t/$tenant",
            "name": "app.page.viewed.v1",
            "id": f"{ACME}:{ME}",
            "data": {"kind": "note"},
        },
    }


async def test_a_person_never_reaches_umami_only_portalr_does(
    stand: Stand, grants: Grants, invite: Invite, ui: Path
) -> None:
    # A browser's request, with its address and agent, through portalr's relay: Umami sees neither.
    relay = Relay(
        Analytics(
            "http://clickhouse:8123",
            KEY,
            writer=httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))),
        ),
        InMemoryConsent(),
        InMemoryRateLimiter(),
        umami=umami_of(stand),
    )
    await relay.consent.give("alice", yes=True)
    app = app_for(grants, Readers(analytics=relay.analytics), invite, ui, relay=relay)
    browser = {
        "x-user": "alice",
        "x-tenant": "acme",
        "x-forwarded-for": "203.0.113.7",
        "x-real-ip": "203.0.113.7",
        "user-agent": "Mozilla/5.0 (Macintosh) Firefox/140.0",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        signed = (await client.post("/v1/analytics/session", headers=browser)).json()["session"]
        response = await client.post(
            "/v1/events",
            json={
                "session": signed,
                "events": [{"event": "app.page.viewed.v1", "route": "/t/$tenant"}],
            },
            headers=browser,
        )
    assert response.json()["recorded"] == 1
    await asyncio.gather(*relay.copies)
    (sent,) = stand.sent
    assert sent.headers["user-agent"] == AGENT
    said = json.dumps(dict(sent.headers)) + sent.content.decode()
    assert "203.0.113.7" not in said
    assert "Firefox" not in said


async def test_umami_down_or_wrong_never_changes_what_was_recorded_nor_raises(
    stand: Stand, caplog: pytest.LogCaptureFixture
) -> None:
    clickhouse = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    for umami in (
        umami_of(Stand()),  # each a fresh Stand, the first up
        Umami(
            "http://umami:3000",
            WEBSITE,
            "pw",
            httpx.AsyncClient(transport=httpx.MockTransport(_refused)),
        ),
        Umami("not a url", WEBSITE, "pw"),
        Umami(
            "http://umami:3000",
            WEBSITE,
            "pw",
            httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))),
        ),
    ):
        relay = Relay(
            Analytics("http://clickhouse:8123", KEY, writer=clickhouse),
            InMemoryConsent(),
            InMemoryRateLimiter(),
            umami=umami,
        )
        await relay.answer("alice", yes=True)
        assert (await relay.record("acme", "alice", BATCH, "s")).recorded == 1
        await asyncio.gather(*relay.copies)
    assert "ConnectError" in caplog.text
    # A 200 without a token, or an address that isn't one: a deletion not done, and nothing raised.
    tokenless = Umami(
        "http://umami:3000",
        WEBSITE,
        "pw",
        httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))),
    )
    assert not await tokenless.forget(ME)
    assert not await Umami("not a url", WEBSITE, "pw").forget(ME)
    assert "UnsupportedProtocol" in caplog.text or "InvalidURL" in caplog.text


def _refused(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


async def test_after_a_failure_the_copies_rest_and_send_nothing(stand: Stand) -> None:
    umami = umami_of(stand)
    stand.down = True
    assert not await umami.send("acme", ME, [("app.page.viewed.v1", {})])
    stand.down = False
    assert not await umami.send("acme", ME, [("app.page.viewed.v1", {})])
    assert len(stand.sent) == 1, "resting: the second wasn't sent"


async def test_a_no_while_the_copy_is_sent_deletes_it_from_umami(stand: Stand) -> None:
    relay = Relay(
        Analytics(
            "http://clickhouse:8123",
            KEY,
            writer=httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))),
        ),
        InMemoryConsent(),
        InMemoryRateLimiter(),
        umami=umami_of(stand),
    )
    await relay.answer("alice", yes=True)

    async def says_no() -> None:
        await relay.consent.give("alice", yes=False)
        stand.sessions["s9"] = f"{ACME}:{ME}"  # as Umami makes it, from the copy

    stand.after_send.append(says_no)
    await relay.record("acme", "alice", BATCH, "s")
    await asyncio.gather(*relay.copies)
    assert not [i for i, d in stand.sessions.items() if d.endswith(f":{ME}")], "deleted there too"
    assert await relay.consent.owes("alice") is None, "and settled"


async def test_forgetting_deletes_the_persons_sessions_exactly_in_every_tenant_or_one(
    stand: Stand,
) -> None:
    umami = umami_of(stand)
    assert await umami.forget(ME, "globex")
    assert set(stand.sessions) == {"s1", "s3"}, "acme's stays, and another person's"
    assert await umami.forget(ME)
    assert set(stand.sessions) == {"s3"}, "a distinct id that only starts like theirs stays"


def searches(stand: Stand) -> int:
    return len([r for r in stand.sent if r.method == "GET" and r.url.path.endswith("/sessions")])


async def test_forgetting_reads_every_page_of_the_search_in_one_round(stand: Stand) -> None:
    stand.sessions = {f"s{n:03}": f"{ACME}:{ME}" for n in range(PAGE * 2 + 5)}
    stand.sessions["other"] = f"{ACME}:someone"
    assert await umami_of(stand).forget(ME)
    assert set(stand.sessions) == {"other"}
    # Three pages in the first round, and one page, empty, in the second, which ends it.
    assert searches(stand) == 3 + 1


async def test_a_session_made_between_rounds_is_found_by_the_next(stand: Stand) -> None:
    made: list[bool] = []

    def another() -> None:
        if not made:
            made.append(True)
            stand.sessions["late"] = f"{ACME}:{ME}"

    stand.after_delete.append(another)
    assert await umami_of(stand).forget(ME)
    assert set(stand.sessions) == {"s3"}
    assert searches(stand) == 3, "a round for the first, one for the late one, one to end"


async def test_a_session_umami_keeps_after_every_round_is_a_deletion_not_done(stand: Stand) -> None:
    stand.stuck = "s1"
    assert not await umami_of(stand).forget(ME)
    deletes = [r for r in stand.sent if r.method == "DELETE" and r.url.path.endswith("/s1")]
    assert len(deletes) == MOST_ROUNDS


async def test_a_deletion_umami_refuses_is_said(stand: Stand) -> None:
    stand.down = True
    assert not await umami_of(stand).forget(ME)
    assert len(stand.sessions) == 3


async def test_the_relay_deletes_with_a_no_and_owes_it_while_umami_is_down(stand: Stand) -> None:
    writer = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    relay = Relay(
        Analytics("http://clickhouse:8123", KEY, writer=writer),
        InMemoryConsent(),
        InMemoryRateLimiter(),
        umami=umami_of(stand),
    )
    await relay.record("acme", "alice", BATCH, "s")
    await asyncio.gather(*relay.copies)
    assert stand.sent == [], "no yes, nothing sent"
    await relay.answer("alice", yes=True)
    assert (await relay.answer("alice", yes=False)).deleted is True
    assert set(stand.sessions) == {"s3"}
    stand.sessions["s4"] = f"{ACME}:{ME}"
    stand.down = True
    await relay.consent.give("alice", yes=True)
    assert (await relay.answer("alice", yes=False)).deleted is False
    assert await relay.consent.owes("alice") is not None
    stand.down = False
    assert await relay.settle_owed() == 1
    assert set(stand.sessions) == {"s3"}


def test_the_password_isnt_in_the_repr() -> None:
    assert "pw" not in repr(Umami("http://umami:3000", WEBSITE, "pw"))


async def test_a_session_gone_before_it_is_deleted_is_no_failure(stand: Stand) -> None:
    stand.vanished = "s1"
    umami = umami_of(stand)
    assert await umami.forget(ME, "acme")
    assert await umami.sessions(ME) == ["s2"]


def relay_of(stand: Stand, consent: InMemoryConsent | None = None) -> Relay:
    writer = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    return Relay(
        Analytics("http://clickhouse:8123", KEY, writer=writer),
        consent or InMemoryConsent(),
        InMemoryRateLimiter(),
        umami=umami_of(stand),
    )


async def test_a_no_while_a_copy_fails_halfway_still_deletes_what_it_made(stand: Stand) -> None:
    relay = relay_of(stand)
    await relay.answer("alice", yes=True)
    stand.sends_taken = 1  # the first event makes the session; the second is a 503

    async def says_no() -> None:
        await relay.consent.give("alice", yes=False)
        stand.sessions["s9"] = f"{ACME}:{ME}"

    stand.after_send.append(says_no)
    two = Batch(
        session="s", events=[Event(event="app.page.viewed.v1"), Event(event="app.thread.opened.v1")]
    )
    await relay.record("acme", "alice", two, "s")
    await asyncio.gather(*relay.copies)
    assert "s9" not in stand.sessions
    assert await relay.consent.owes("alice") is None, "deleted, and settled"


class Unreadable(InMemoryConsent):
    """Answers that can't be read once the batch is written."""

    reads = 0

    async def given(self, user_id: str) -> bool:
        self.reads += 1
        if self.reads > 2:
            raise RuntimeError(user_id)
        return await super().given(user_id)


async def test_an_answer_that_cant_be_read_again_owes_a_deletion(
    stand: Stand, caplog: pytest.LogCaptureFixture
) -> None:
    consent = Unreadable()
    relay = relay_of(stand, consent)
    await consent.give("alice", yes=True)
    await relay.record("acme", "alice", BATCH, "s")
    await asyncio.gather(*relay.copies)
    assert await consent.owes("alice") is not None
    assert "couldn't be checked: RuntimeError" in caplog.text


async def test_past_the_most_copies_a_batchs_copy_is_dropped_not_queued(stand: Stand) -> None:
    relay = relay_of(stand)
    await relay.answer("alice", yes=True)
    held = [asyncio.get_running_loop().create_future() for _ in range(MOST_COPIES)]
    relay.copies.update(held)
    assert (await relay.record("acme", "alice", BATCH, "s")).recorded == 1
    assert len(relay.copies) == MOST_COPIES
    assert stand.sent == []
    for future in held:
        future.cancel()


async def test_an_event_umami_refuses_is_dropped_alone_and_the_copies_dont_rest(
    stand: Stand,
) -> None:
    stand.refused = {"app.thread.opened.v1"}
    umami = umami_of(stand)
    events = [("app.thread.opened.v1", {}), ("app.page.viewed.v1", {})]
    assert not await umami.send("acme", ME, events)
    assert await umami.send("acme", ME, [("app.page.viewed.v1", {})])
    assert len(stand.sent) == 3, "both of the first, and the next at once"


class Broken(Unreadable):
    """Answers that can't be read once the batch is written, nor owe a deletion."""

    async def owe(self, user_id: str) -> int:
        raise RuntimeError(user_id)


async def test_a_deletion_that_cant_be_owed_either_is_said_for_operators(
    stand: Stand, caplog: pytest.LogCaptureFixture
) -> None:
    consent = Broken()
    relay = relay_of(stand, consent)
    await consent.give("alice", yes=True)
    await relay.record("acme", "alice", BATCH, "s")
    await asyncio.gather(*relay.copies)
    assert "a deletion couldn't be owed: RuntimeError" in caplog.text


def test_a_distinct_id_fits_umamis_whatever_the_tenants_id() -> None:
    longest = "t" * 256
    assert len(distinct(longest, ME)) <= DISTINCT_LENGTH
    assert distinct(longest, ME).rpartition(":")[2] == ME
    assert distinct("acme", ME) != distinct("globex", ME)


async def test_a_removal_from_a_tenant_deletes_that_tenants_session_in_umami_alone(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("portalr.analytics.relay.REMOVAL_GRACE", timedelta(0))
    relay = relay_of(stand)
    await relay.removed("globex", "alice")
    stand.down = True
    assert await relay.settle_owed() == 0, "owed while Umami is down"
    stand.down = False
    assert await relay.settle_owed() == 1
    assert set(stand.sessions) == {"s1", "s3"}, "acme's stays, found by globex's hash alone"
    assert await relay.consent.removals_owed(100) == []
