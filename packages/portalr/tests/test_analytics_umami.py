"""Umami: a copy of consented events, from portalr's own agent, and a person's deletion there."""

import json

import httpx
import pytest

from portalr.analytics import InMemoryConsent, InMemoryRateLimiter, Relay, Umami
from portalr.analytics.relay import Batch, Event
from portalr.readers import Analytics
from portalr.readers.analytics import distinct_id
from portalr.readers.umami import AGENT

KEY = b"the deployment's key"
WEBSITE = "446fed1e-11a4-4c5f-9b72-31e6d4cf882d"
ME = distinct_id(KEY, "alice")


class Stand:
    """Umami, as a test scripts it: its sessions, by id and distinct id, and what it was sent."""

    def __init__(self) -> None:
        self.sent: list[httpx.Request] = []
        self.sessions = {"s1": f"acme:{ME}", "s2": f"globex:{ME}", "s3": f"acme:{ME}x"}
        self.down = False
        self.gone: str | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        if self.down:
            return httpx.Response(503)
        path = request.url.path
        if path == "/api/auth/login":
            assert json.loads(request.content) == {"username": "portalr", "password": "pw"}
            return httpx.Response(200, json={"token": "t0k"})
        if path == "/api/send":
            return httpx.Response(200, json={"cache": "c"})
        if path == f"/api/websites/{WEBSITE}/sessions":
            assert request.headers["authorization"] == "Bearer t0k"
            found = [
                {"id": i} for i, d in self.sessions.items() if request.url.params["search"] in d
            ]
            return httpx.Response(200, json={"data": found})
        session = path.rsplit("/", 1)[1]
        if request.method == "DELETE":
            if session == self.gone:
                return httpx.Response(500)
            del self.sessions[session]
            return httpx.Response(200)
        return httpx.Response(200, json={"id": session, "distinctId": self.sessions[session]})


@pytest.fixture
def stand() -> Stand:
    return Stand()


@pytest.fixture
def umami(stand: Stand) -> Umami:
    return Umami(
        "http://umami:3000", WEBSITE, "pw", httpx.AsyncClient(transport=httpx.MockTransport(stand))
    )


async def test_each_event_goes_as_the_tenants_person_from_portalrs_own_agent(
    umami: Umami, stand: Stand
) -> None:
    sent = await umami.send("acme", ME, [("app.page.viewed.v1", {"route": "/t/$tenant"})])
    assert sent
    (request,) = stand.sent
    assert request.headers["user-agent"] == AGENT
    assert "x-forwarded-for" not in request.headers
    assert json.loads(request.content) == {
        "type": "event",
        "payload": {
            "website": WEBSITE,
            "hostname": "portalr.internal",
            "url": "/t/$tenant",
            "name": "app.page.viewed.v1",
            "id": f"acme:{ME}",
            "data": {},
        },
    }


async def test_a_send_umami_refuses_or_doesnt_answer_is_logged_and_dropped(
    umami: Umami, stand: Stand, caplog: pytest.LogCaptureFixture
) -> None:
    stand.down = True
    assert not await umami.send("acme", ME, [("app.page.viewed.v1", {})])
    failing = Umami(
        "http://umami:3000",
        WEBSITE,
        "pw",
        httpx.AsyncClient(transport=httpx.MockTransport(_refused)),
    )
    assert not await failing.send("acme", ME, [("app.page.viewed.v1", {})])
    assert "ConnectError" in caplog.text


def _refused(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


async def test_forgetting_deletes_the_persons_sessions_exactly_in_every_tenant_or_one(
    umami: Umami, stand: Stand
) -> None:
    assert await umami.forget(ME, "globex")
    assert set(stand.sessions) == {"s1", "s3"}, "acme's stays, and another person's"
    assert await umami.forget(ME)
    assert set(stand.sessions) == {"s3"}, "a distinct id that only starts like theirs stays"


async def test_a_deletion_umami_refuses_is_said(umami: Umami, stand: Stand) -> None:
    stand.down = True
    assert not await umami.forget(ME)
    assert len(stand.sessions) == 3


async def test_the_relay_copies_consented_events_and_deletes_with_a_no(stand: Stand) -> None:
    writer = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    relay = Relay(
        Analytics("http://clickhouse:8123", KEY, writer=writer),
        InMemoryConsent(),
        InMemoryRateLimiter(),
        umami=Umami(
            "http://umami:3000",
            WEBSITE,
            "pw",
            httpx.AsyncClient(transport=httpx.MockTransport(stand)),
        ),
    )
    batch = Batch(session="s", events=[Event(event="app.page.viewed.v1", route="/t/$tenant")])
    await relay.record("acme", "alice", batch, "sess")
    assert stand.sent == [], "no yes, nothing sent"
    await relay.answer("alice", yes=True)
    await relay.record("acme", "alice", batch, "sess")
    assert [r.url.path for r in stand.sent] == ["/api/send"]
    said = await relay.answer("alice", yes=False)
    assert said.deleted is True
    assert set(stand.sessions) == {"s3"}
    # Umami down: the deletion stays owed, and is done once it answers.
    stand.sessions["s4"] = f"acme:{ME}"
    stand.down = True
    await relay.consent.give("alice", yes=True)
    assert (await relay.answer("alice", yes=False)).deleted is False
    assert await relay.consent.owes("alice") is not None
    stand.down = False
    assert await relay.settle_owed() == 1
    assert set(stand.sessions) == {"s3"}


def test_the_password_isnt_in_the_repr() -> None:
    assert "pw" not in repr(Umami("http://umami:3000", WEBSITE, "pw"))


async def test_a_session_umami_wont_delete_is_said(umami: Umami, stand: Stand) -> None:
    stand.gone = "s1"
    assert not await umami.forget(ME, "acme")
