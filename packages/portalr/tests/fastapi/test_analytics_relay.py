"""The relay: a signed-in person's events, with their yes, in their tenant, as the registry says."""

import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from grantr.core import AuditEntry, ServicePrincipal, User
from grantr.grants import Grants
from portalr.analytics import InMemoryConsent, InMemoryRateLimiter, Relay
from portalr.analytics.relay import (
    MOST_BYTES,
    MOST_EVENTS,
    REMOVALS,
    SESSION_HOURS,
    Batch,
    Event,
    Relayed,
)
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
        self.after_insert: Callable[[], Awaitable[object]] | None = None

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status = self.status
        if self.after_insert is not None and "INSERT" in request.url.params.get("query", ""):
            await self.after_insert()
        return httpx.Response(status)

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
def relay(clickhouse: ClickHouse, grants: Grants) -> Relay:
    writer = httpx.AsyncClient(transport=httpx.MockTransport(clickhouse))
    return Relay(
        Analytics("http://clickhouse:8123", KEY, writer=writer),
        InMemoryConsent(),
        InMemoryRateLimiter(per_second=1, burst=30),
        grants=grants,
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
    assert (await client.get("/v1/analytics/consent", headers=ALICE)).json() == {
        "given": False,
        "deleting": False,
    }
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


def deletions(clickhouse: ClickHouse) -> int:
    return sum("DELETE" in r.content.decode() for r in clickhouse.requests)


async def test_taking_a_yes_back_deletes_the_persons_events_at_once_and_only_then(
    client: httpx.AsyncClient, clickhouse: ClickHouse
) -> None:
    said = await client.put("/v1/analytics/consent", json={"given": False}, headers=ALICE)
    assert said.json() == {"given": False, "deleted": None}, "never a yes: nothing to delete"
    await say_yes(client)
    said = await client.put("/v1/analytics/consent", json={"given": False}, headers=ALICE)
    assert said.json() == {"given": False, "deleted": True}
    (deletion,) = clickhouse.requests
    assert deletion.url.params["param_person"] == distinct_id(KEY, "alice")
    said = await client.put("/v1/analytics/consent", json={"given": False}, headers=ALICE)
    assert said.json() == {"given": False, "deleted": None}, "a no again deletes nothing more"
    assert deletions(clickhouse) == 1


async def test_a_deletion_clickhouse_cant_take_stays_owed_until_it_can(
    client: httpx.AsyncClient, clickhouse: ClickHouse, relay: Relay
) -> None:
    await say_yes(client)
    clickhouse.status = 503
    said = await client.put("/v1/analytics/consent", json={"given": False}, headers=ALICE)
    assert said.json() == {"given": False, "deleted": False}
    assert await relay.consent.owes("alice")
    await client.get("/v1/analytics/consent", headers=ALICE)
    assert await relay.consent.owes("alice"), "still down: still owed"
    clickhouse.status = 200
    await client.get("/v1/analytics/consent", headers=ALICE)
    assert await relay.consent.owes("alice") is None, "tried again on the next request"
    assert deletions(clickhouse) == 3


async def test_deletions_owed_are_done_as_a_replica_starts(
    clickhouse: ClickHouse, relay: Relay
) -> None:
    for person in ("alice", "bob"):
        await relay.consent.give(person, yes=True)
    clickhouse.status = 503
    for person in ("alice", "bob"):
        await relay.answer(person, yes=False)
    clickhouse.status = 200
    assert await relay.settle_owed() == 2
    assert await relay.consent.owing(100) == []


async def test_a_no_that_lands_while_a_batch_is_written_deletes_the_batch_too(
    client: httpx.AsyncClient, clickhouse: ClickHouse, relay: Relay
) -> None:
    await say_yes(client)
    signed = await session(client)

    # The person says no while their batch is in flight.
    clickhouse.after_insert = lambda: relay.consent.give("alice", yes=False)
    sent = await client.post(
        "/v1/events", json={"session": signed, "events": [page()]}, headers=ALICE
    )
    assert sent.json() == {"recorded": 0, "dropped": 1}
    assert [
        ("INSERT" in r.url.params.get("query", ""), "DELETE" in r.content.decode())
        for r in clickhouse.requests
    ] == [(True, False), (False, True)]
    assert await relay.consent.owes("alice") is None


async def test_a_session_that_isnt_ascii_is_refused_not_failed(client: httpx.AsyncClient) -> None:
    await say_yes(client)
    for signed in ("1-2.é", "é.é", "1-2.\u00ff" * 3):
        sent = await client.post(
            "/v1/events", json={"session": signed, "events": [page()]}, headers=ALICE
        )
        assert sent.status_code == 403, signed


async def test_a_body_over_the_cap_is_refused_as_it_comes_or_as_it_is_declared(
    client: httpx.AsyncClient,
) -> None:
    await say_yes(client)

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(64):
            yield b" " * 1024

    streamed = await client.post("/v1/events", content=chunks(), headers=ALICE)
    assert streamed.status_code == 413
    declared = await client.post(
        "/v1/events", content=b"{}", headers={**ALICE, "content-length": str(MOST_BYTES + 1)}
    )
    assert declared.status_code == 413


async def test_a_person_making_too_many_requests_is_slowed_before_anything_is_read(
    grants: Grants, invite: Invite, ui: Path, relay: Relay
) -> None:
    slow = Relay(
        relay.analytics, relay.consent, relay.limiter, InMemoryRateLimiter(per_second=1, burst=2)
    )
    app = app_for(grants, Readers(analytics=slow.analytics), invite, ui, relay=slow)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        codes = [
            (await client.get("/v1/analytics/consent", headers=ALICE)).status_code for _ in range(3)
        ]
    assert codes == [200, 200, 429]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        for answer in (True, False, True, False):
            withdrawn = await client.put(
                "/v1/analytics/consent", json={"given": answer}, headers=ALICE
            )
            assert withdrawn.status_code == 200, "an answer is never refused for the pace"


async def test_only_the_registrys_values_are_kept_however_written(
    client: httpx.AsyncClient, clickhouse: ClickHouse
) -> None:
    await say_yes(client)
    events = [
        {"event": "app.integration.used.v1", "props": {"integration": "tracker"}},
        {"event": "app.integration.used.v1", "props": {"integration": "someone\uff20example.com"}},
        {"event": "app.artifact.opened.v1", "props": {"kind": "note"}},
        {"event": "app.artifact.opened.v1", "props": {"kind": "my secret plan"}},
    ]
    await client.post(
        "/v1/events", json={"session": await session(client), "events": events}, headers=ALICE
    )
    assert [row["props"] for row in clickhouse.rows()] == [
        {"integration": "tracker"},
        {},
        {"kind": "note"},
        {},
    ]


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


async def test_a_no_that_lands_after_the_last_deletion_still_owes_the_straggler(
    client: httpx.AsyncClient, clickhouse: ClickHouse, relay: Relay
) -> None:
    await say_yes(client)
    signed = await session(client)

    async def no_and_settled_then_clickhouse_down() -> None:
        # The person's no lands, and its deletion is done, before the straggler's write returns;
        # then ClickHouse goes down, so the straggler's own deletion fails.
        await relay.answer("alice", yes=False)
        clickhouse.status = 503

    clickhouse.after_insert = no_and_settled_then_clickhouse_down
    await client.post("/v1/events", json={"session": signed, "events": [page()]}, headers=ALICE)
    assert await relay.consent.owes("alice") is not None, "the straggler's deletion is owed"
    assert not await relay.consent.given("alice")


async def test_a_yes_given_while_a_straggler_is_deleted_stays_a_yes(
    clickhouse: ClickHouse, relay: Relay
) -> None:
    class Wavering(InMemoryConsent):
        """Yes before the write, no just after it, yes again as the straggler is deleted."""

        def __init__(self) -> None:
            super().__init__()
            self.answers = iter([True, False])

        async def given(self, user_id: str) -> bool:
            return next(self.answers, await super().given(user_id))

    consent = Wavering()
    await consent.give("alice", yes=True)
    wavering = Relay(relay.analytics, consent, relay.limiter)
    batch = Batch(session="s", events=[Event(event="app.page.viewed.v1")])
    assert await wavering.record("acme", "alice", batch, "s") == Relayed(recorded=0, dropped=1)
    assert await consent.given("alice"), "the deletion owed never touched the person's yes"
    assert [("INSERT" in r.url.params.get("query", "")) for r in clickhouse.requests] == [
        True,
        False,
    ]


async def test_a_late_deletion_never_clears_a_newer_one(
    clickhouse: ClickHouse, relay: Relay
) -> None:
    await relay.consent.give("alice", yes=True)
    first = await relay.consent.give("alice", yes=False)
    await relay.consent.give("alice", yes=True)
    await relay.consent.give("alice", yes=False)
    clickhouse.status = 200
    assert first is not None
    assert await relay.settle("alice", first)
    assert await relay.consent.owes("alice") is not None


async def test_answers_drain_the_persons_pace_but_are_never_refused(
    grants: Grants, invite: Invite, ui: Path, relay: Relay
) -> None:
    paced = Relay(
        relay.analytics, relay.consent, relay.limiter, InMemoryRateLimiter(per_second=1, burst=3)
    )
    app = app_for(grants, Readers(analytics=paced.analytics), invite, ui, relay=paced)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        for _ in range(3):
            said = await client.put("/v1/analytics/consent", json={"given": True}, headers=ALICE)
            assert said.status_code == 200
        assert (await client.get("/v1/analytics/consent", headers=ALICE)).status_code == 429


async def test_a_loop_of_yes_and_no_sets_off_so_many_deletions_and_owes_the_rest(
    client: httpx.AsyncClient, clickhouse: ClickHouse, relay: Relay
) -> None:
    for _ in range(15):
        await client.put("/v1/analytics/consent", json={"given": True}, headers=ALICE)
        await client.put("/v1/analytics/consent", json={"given": False}, headers=ALICE)
    assert deletions(clickhouse) == 10, "the person's ten an hour"
    assert await relay.consent.owes("alice") is not None, "the rest stays owed"
    assert await relay.settle_owed() == 1, "the background pass isn't paced"
    assert await relay.consent.owes("alice") is None
    assert deletions(clickhouse) == 11


async def test_a_pass_settles_so_many_people_at_most(clickhouse: ClickHouse, relay: Relay) -> None:
    for person in ("alice", "bob", "carol"):
        await relay.consent.give(person, yes=True)
        await relay.consent.give(person, yes=False)
    assert await relay.settle_owed(most=2) == 2
    assert [person for person, _ in await relay.consent.owing(100)] == ["carol"]


@pytest.mark.parametrize("given", [0, 1, "true", "no", None])
async def test_an_answer_is_true_or_false_and_nothing_like_it(
    client: httpx.AsyncClient, given: object
) -> None:
    said = await client.put("/v1/analytics/consent", json={"given": given}, headers=ALICE)
    assert said.status_code == 422


async def test_a_batch_is_taken_as_it_is_written_and_not_coerced(
    client: httpx.AsyncClient,
) -> None:
    await say_yes(client)
    signed = await session(client)
    for event in ({"event": 1}, {"event": "app.page.viewed.v1", "props": {"kind": 3}}):
        sent = await client.post(
            "/v1/events", json={"session": signed, "events": [event]}, headers=ALICE
        )
        assert sent.status_code == 422, event


async def test_a_deletion_still_owed_is_read_with_the_answer_until_it_is_done(
    client: httpx.AsyncClient, clickhouse: ClickHouse
) -> None:
    await say_yes(client)
    clickhouse.status = 503
    await client.put("/v1/analytics/consent", json={"given": False}, headers=ALICE)
    read = await client.get("/v1/analytics/consent", headers=ALICE)
    assert read.json() == {"given": False, "deleting": True}
    clickhouse.status = 200
    read = await client.get("/v1/analytics/consent", headers=ALICE)
    assert read.json() == {"given": False, "deleting": False}


async def test_the_pass_owes_a_removal_from_grantrs_log_and_deletes_it_once_its_grace_has_passed(
    relay: Relay, clickhouse: ClickHouse, grants: Grants, monkeypatch: pytest.MonkeyPatch
) -> None:
    await grants.remove_member("acme", User(id="bob"), by=User(id="alice"))
    assert clickhouse.requests == [], "the admin's removal never waits on ClickHouse"
    assert await relay.settle_owed() == 0, "not before its grace has passed"
    assert clickhouse.requests == []
    ((user, tenant, removed_at),) = await relay.consent.removals_owed(100)
    assert (user, tenant) == ("bob", "acme")
    (entry,) = await grants.served_audit("acme", keep=REMOVALS)
    assert removed_at == entry.at, "owed up to the removal's entry, not the pass's clock"
    monkeypatch.setattr("portalr.analytics.relay.REMOVAL_GRACE", timedelta(0))
    assert await relay.settle_owed() == 1
    (deletion,) = clickhouse.requests
    params = deletion.url.params
    assert deletion.content.decode() == (
        "DELETE FROM analytics.events WHERE distinct_id = {person:FixedString(32)}"
        " AND tenant_id = {tenant:String} AND ts <= {until:DateTime64(3, 'UTC')}"
    )
    assert params["param_person"] == distinct_id(KEY, "bob")
    assert params["param_tenant"] == "acme"
    # A few seconds past the removal, for a relaying replica's clock that runs ahead.
    until = datetime.strptime(params["param_until"], "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=UTC)
    assert timedelta(seconds=4.99) <= until - removed_at <= timedelta(seconds=5)
    assert await relay.consent.removals_owed(100) == [], "done, so no longer owed"
    assert await relay.settle_owed() == 0
    assert len(clickhouse.requests) == 1, "a removal read once is not owed again"


async def test_a_removals_deletion_clickhouse_refuses_stays_owed_and_is_done_later(
    relay: Relay, clickhouse: ClickHouse, grants: Grants, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("portalr.analytics.relay.REMOVAL_GRACE", timedelta(0))
    await grants.remove_member("acme", User(id="bob"), by=User(id="alice"))
    clickhouse.status = 503
    assert await relay.settle_owed() == 0
    assert [(u, t) for u, t, _ in await relay.consent.removals_owed(100)] == [("bob", "acme")]
    clickhouse.status = 200
    assert await relay.settle_owed() == 1
    assert await relay.consent.removals_owed(100) == []
    # The same moment, each time it is tried: events written after the removal stay.
    assert len({r.url.params["param_until"] for r in clickhouse.requests}) == 1


async def test_a_removal_is_owed_by_a_relay_that_started_after_it(grants: Grants) -> None:
    await grants.remove_member("acme", User(id="bob"), by=User(id="alice"))
    started_later = Relay(
        Analytics("http://clickhouse:8123", KEY),
        InMemoryConsent(),
        InMemoryRateLimiter(),
        grants=grants,
    )
    await started_later.settle_owed()
    owed = await started_later.consent.removals_owed(100)
    assert [(u, t) for u, t, _ in owed] == [("bob", "acme")]


async def test_the_pass_reads_each_tenants_log_on_from_where_it_stopped_and_owes_no_key(
    relay: Relay, grants: Grants
) -> None:
    alice, carol = User(id="alice"), User(id="carol")
    await grants.add_member("acme", User(id="dave"), by=alice)
    await grants.add_member("globex", ServicePrincipal(id="ci"), by=carol)
    await grants.add_member("globex", User(id="erin"), by=carol)
    for tenant, member, by in (
        ("acme", User(id="bob"), alice),
        ("acme", User(id="dave"), alice),
        ("globex", ServicePrincipal(id="ci"), carol),
        ("globex", User(id="erin"), carol),
    ):
        await grants.remove_member(tenant, member, by=by)

    async def owed() -> list[tuple[str, str]]:
        return [(user, tenant) for user, tenant, _ in await relay.consent.removals_owed(100)]

    await relay.settle_owed(most=1)
    assert await owed() == [("bob", "acme")], "one entry of each tenant's log, the key's skipped"
    await relay.settle_owed(most=1)
    assert await owed() == [("bob", "acme"), ("dave", "acme"), ("erin", "globex")]
    await relay.settle_owed(most=1)
    assert len(await owed()) == 3, "read to the end"
    for tenant in ("acme", "globex"):
        *_, last = await grants.served_audit(tenant, keep=REMOVALS)
        assert await relay.consent.audit_cursor(tenant) == last.seq


class Failing(InMemoryConsent):
    """Answers that fail to owe the second removal asked of them, once."""

    def __init__(self) -> None:
        super().__init__()
        self.owed = 0
        self.fail = True

    async def owe_removal(self, user_id: str, tenant: str, removed_at: datetime) -> None:
        self.owed += 1
        if self.fail and self.owed == 2:
            raise RuntimeError("the database went away")
        await super().owe_removal(user_id, tenant, removed_at)


async def test_the_mark_stays_where_it_was_if_owing_fails_partway(
    clickhouse: ClickHouse, grants: Grants, caplog: pytest.LogCaptureFixture
) -> None:
    alice = User(id="alice")
    await grants.add_member("acme", User(id="dave"), by=alice)
    for member in ("bob", "dave"):
        await grants.remove_member("acme", User(id=member), by=alice)
    consent = Failing()
    relay = Relay(
        Analytics("http://clickhouse:8123", KEY), consent, InMemoryRateLimiter(), grants=grants
    )
    with caplog.at_level(logging.ERROR):
        await relay.settle_owed()
    assert "RuntimeError" in caplog.text
    assert await consent.audit_cursor("acme") == 0
    consent.fail = False
    await relay.settle_owed()
    assert {(u, t) for u, t, _ in await consent.removals_owed(100)} == {
        ("bob", "acme"),
        ("dave", "acme"),
    }
    *_, last = await grants.served_audit("acme", keep=REMOVALS)
    assert await consent.audit_cursor("acme") == last.seq


async def test_a_tenant_whose_log_cant_be_read_holds_up_neither_the_rest_nor_the_deletions(
    relay: Relay,
    clickhouse: ClickHouse,
    grants: Grants,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr("portalr.analytics.relay.REMOVAL_GRACE", timedelta(0))
    await grants.remove_member("acme", User(id="bob"), by=User(id="alice"))
    assert await relay.settle_owed() == 1
    clickhouse.requests.clear()
    await grants.add_member("globex", User(id="erin"), by=User(id="carol"))
    await grants.remove_member("globex", User(id="erin"), by=User(id="carol"))
    await grants.add_member("acme", User(id="bob"), by=User(id="alice"))
    await grants.remove_member("acme", User(id="bob"), by=User(id="alice"))
    read = grants.served_audit

    async def unreadable(tenant: str, **kept: Any) -> list[AuditEntry]:
        if tenant == "acme":
            raise RuntimeError("the database went away")
        return await read(tenant, **kept)

    monkeypatch.setattr(grants, "served_audit", unreadable)
    with caplog.at_level(logging.ERROR):
        assert await relay.settle_owed() == 1, "globex's removal is owed and deleted"
    assert "tenant acme's removals weren't read: RuntimeError" in caplog.text
    assert [r.url.params["param_tenant"] for r in clickhouse.requests] == ["globex"]


async def test_tenants_that_cant_be_listed_hold_up_no_deletion(
    relay: Relay,
    clickhouse: ClickHouse,
    grants: Grants,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr("portalr.analytics.relay.REMOVAL_GRACE", timedelta(0))
    await relay.consent.owe_removal("bob", "acme", datetime.now(UTC))

    async def unreadable() -> list[str]:
        raise RuntimeError("the database went away")

    monkeypatch.setattr(grants, "served_tenants", unreadable)
    with caplog.at_level(logging.ERROR):
        assert await relay.settle_owed() == 1
    assert "the tenants weren't listed: RuntimeError" in caplog.text
