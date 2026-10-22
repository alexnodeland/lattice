"""The relay: a signed-in person's events, with their yes, in their tenant, as the registry says."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from grantr.grants import Grants
from portalr.analytics import InMemoryConsent, InMemoryRateLimiter, Relay
from portalr.analytics.relay import MOST_BYTES, MOST_EVENTS, SESSION_HOURS
from portalr.invites import Invite
from portalr.readers import Analytics, Readers
from portalr.readers.analytics import distinct_id

from .conftest import app_for

KEY = b"the deployment's key"
ALICE = {"x-user": "alice", "x-tenant": "acme"}


class ClickHouse:
    """What the relay sent ClickHouse, answering each as told."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status)

    def rows(self) -> list[dict[str, object]]:
        return [
            json.loads(line)
            for request in self.requests
            if "INSERT" in request.url.params.get("query", "")
            for line in request.content.decode().splitlines()
        ]


@pytest.fixture
def clickhouse() -> ClickHouse:
    return ClickHouse()


@pytest.fixture
def relay(clickhouse: ClickHouse) -> Relay:
    writer = httpx.AsyncClient(transport=httpx.MockTransport(clickhouse))
    return Relay(
        Analytics("http://clickhouse:8123", KEY, writer=writer),
        InMemoryConsent(),
        InMemoryRateLimiter(per_second=1, burst=30),
    )


@pytest.fixture
async def client(
    grants: Grants, invite: Invite, ui: Path, relay: Relay
) -> AsyncIterator[httpx.AsyncClient]:
    app = app_for(grants, Readers(analytics=relay.analytics), invite, ui, relay=relay)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        yield client


async def session(client: httpx.AsyncClient, who: dict[str, str] = ALICE) -> str:
    return (await client.post("/v1/analytics/session", headers=who)).json()["session"]


async def say_yes(client: httpx.AsyncClient, who: dict[str, str] = ALICE) -> None:
    answered = await client.put("/v1/analytics/consent", json={"given": True}, headers=who)
    assert answered.json() == {"given": True, "deleted": None}


def page(route: str = "/t/$tenant/w/$workspace/runs", **props: str) -> dict[str, object]:
    return {"event": "app.page.viewed.v1", "route": route, "props": props}


async def test_nothing_is_kept_until_the_person_says_yes(
    client: httpx.AsyncClient, clickhouse: ClickHouse
) -> None:
    assert (await client.get("/v1/analytics/consent", headers=ALICE)).json() == {"given": False}
    sent = await client.post(
        "/v1/events", json={"session": await session(client), "events": [page()]}, headers=ALICE
    )
    assert sent.status_code == 202
    assert sent.json() == {"recorded": 0, "dropped": 1}
    assert clickhouse.requests == []


async def test_with_a_yes_an_event_is_kept_in_the_requests_tenant_and_the_signed_session(
    client: httpx.AsyncClient, clickhouse: ClickHouse
) -> None:
    await say_yes(client)
    signed = await session(client)
    sent = await client.post(
        "/v1/events", json={"session": signed, "events": [page()]}, headers=ALICE
    )
    assert sent.json() == {"recorded": 1, "dropped": 0}
    (row,) = clickhouse.rows()
    assert row["tenant_id"] == "acme"
    assert row["workspace_id"] == ""
    assert row["distinct_id"] == distinct_id(KEY, "alice")
    assert row["session_id"] == signed.partition(".")[0]
    assert row["props"] == {"route": "/t/$tenant/w/$workspace/runs"}


async def test_only_the_registrys_events_keys_and_the_apps_routes_are_kept(
    client: httpx.AsyncClient, clickhouse: ClickHouse
) -> None:
    await say_yes(client)
    events = [
        page(route="/t/acme/w/main/runs?q=secret", extra="x"),
        {"event": "app.integration.used.v1", "props": {"integration": "a@b.com"}},
        {"event": "app.integration.used.v1", "props": {"integration": "tracker", "email": "x"}},
        {"event": "app.made.up.v1"},
    ]
    sent = await client.post(
        "/v1/events", json={"session": await session(client), "events": events}, headers=ALICE
    )
    assert sent.json() == {"recorded": 3, "dropped": 1}
    assert [row["props"] for row in clickhouse.rows()] == [{}, {}, {"integration": "tracker"}]


async def test_a_session_signed_for_another_person_or_too_old_is_refused(
    client: httpx.AsyncClient, relay: Relay
) -> None:
    await say_yes(client)
    bobs = relay.sign("bob")
    stale = relay.sign("alice", now=0)
    for signed in (bobs, stale, "made-up", "1-2.0000"):
        sent = await client.post(
            "/v1/events", json={"session": signed, "events": [page()]}, headers=ALICE
        )
        assert sent.status_code == 403, signed
    assert (
        relay.session_of("alice", relay.sign("alice", now=10), now=10 + SESSION_HOURS * 3600)
        is None
    )


async def test_a_tenant_the_person_isnt_a_member_of_is_refused(
    client: httpx.AsyncClient,
) -> None:
    await say_yes(client)
    signed = await session(client)
    for headers in ({"x-user": "alice", "x-tenant": "globex"}, {"x-user": "alice"}):
        sent = await client.post(
            "/v1/events", json={"session": signed, "events": [page()]}, headers=headers
        )
        assert sent.status_code in (400, 403), headers


async def test_a_key_or_an_agent_sends_no_events(client: httpx.AsyncClient) -> None:
    for path, method in (
        ("/v1/analytics/session", "post"),
        ("/v1/analytics/consent", "get"),
        ("/v1/events", "post"),
    ):
        response = await client.request(
            method, path, headers={"x-principal": "key-1", "x-tenant": "acme"}, json={}
        )
        assert response.status_code == 403, path


async def test_a_batch_too_large_or_too_long_or_malformed_is_refused(
    client: httpx.AsyncClient,
) -> None:
    await say_yes(client)
    signed = await session(client)
    huge = {"session": signed, "events": [page(note="x" * 200)] * 100}
    assert len(json.dumps(huge)) > MOST_BYTES
    assert (await client.post("/v1/events", json=huge, headers=ALICE)).status_code == 413
    many = {"session": signed, "events": [page()] * (MOST_EVENTS + 1)}
    assert (await client.post("/v1/events", json=many, headers=ALICE)).status_code == 422
    long_value = {"session": signed, "events": [page(note="x" * 201)]}
    assert (await client.post("/v1/events", json=long_value, headers=ALICE)).status_code == 422
    assert (await client.post("/v1/events", content=b"{", headers=ALICE)).status_code == 422


async def test_past_the_persons_pace_a_batch_is_refused_with_when_to_try(
    client: httpx.AsyncClient,
) -> None:
    await say_yes(client)
    batch = {"session": await session(client), "events": [page()] * 20}
    assert (await client.post("/v1/events", json=batch, headers=ALICE)).status_code == 202
    refused = await client.post("/v1/events", json=batch, headers=ALICE)
    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "10"


async def test_saying_no_deletes_the_persons_events_at_once(
    client: httpx.AsyncClient, clickhouse: ClickHouse
) -> None:
    await say_yes(client)
    answered = await client.put("/v1/analytics/consent", json={"given": False}, headers=ALICE)
    assert answered.json() == {"given": False, "deleted": True}
    (deletion,) = clickhouse.requests
    assert deletion.url.params["param_person"] == distinct_id(KEY, "alice")
    clickhouse.status = 500
    answered = await client.put("/v1/analytics/consent", json={"given": False}, headers=ALICE)
    assert answered.json() == {"given": False, "deleted": False}


async def test_a_batch_clickhouse_doesnt_take_is_dropped_not_failed(
    client: httpx.AsyncClient, clickhouse: ClickHouse
) -> None:
    await say_yes(client)
    clickhouse.status = 503
    sent = await client.post(
        "/v1/events", json={"session": await session(client), "events": [page()]}, headers=ALICE
    )
    assert sent.status_code == 202
    assert sent.json() == {"recorded": 0, "dropped": 1}


async def test_a_batch_of_unknown_events_writes_nothing(
    client: httpx.AsyncClient, clickhouse: ClickHouse
) -> None:
    await say_yes(client)
    sent = await client.post(
        "/v1/events",
        json={"session": await session(client), "events": [{"event": "app.made.up.v1"}]},
        headers=ALICE,
    )
    assert sent.json() == {"recorded": 0, "dropped": 1}
    assert clickhouse.requests == []
