"""portalr's analytics: each event is the registry's and the server's; each read, the tenant's."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from pydantic import ValidationError

from grantr.core import Agent, ServicePrincipal, User
from portalr.readers import Analytics, Readers
from portalr.readers.analytics import (
    REGISTRY,
    TENANT_SETTING,
    Active,
    ActiveDay,
    Adoption,
    AdoptionQuery,
    Funnel,
    IntegrationUse,
    actor_of,
    distinct_id,
)
from portalr.readers.query import Span
from portalr.readers.reading import Ok, Unavailable
from portalr.tenant import allowed

ACME = allowed("acme")
KEY = b"the deployment's key"
SPAN = Span(start=datetime(2026, 10, 1, tzinfo=UTC), end=datetime(2026, 10, 22, tzinfo=UTC))
URL = "http://clickhouse:8123"


def recorded(answer: httpx.Response) -> tuple[list[httpx.Request], httpx.AsyncClient]:
    """A client that answers every request so, and the requests it was sent."""
    sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return answer

    return sent, httpx.AsyncClient(transport=httpx.MockTransport(handle))


def failing() -> httpx.AsyncClient:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


READS: dict[str, Callable[[Analytics], Awaitable[object]]] = {
    "counts": lambda analytics: analytics.counts(ACME, SPAN),
    "adoption": lambda analytics: analytics.adoption(
        ACME, AdoptionQuery(start=SPAN.start, end=SPAN.end)
    ),
}
"""Every read the analytics reader has: a new one is added here, and held to the tenant below."""


def test_every_read_of_the_reader_is_listed() -> None:
    public = {name for name in vars(Analytics) if not name.startswith("_")}
    writes = {"capture", "capture_many", "forget", "url", "key", "writer", "reader"}
    assert public - writes == set(READS)


@pytest.mark.parametrize("name", sorted(READS))
async def test_every_analytics_query_carries_the_tenant_twice(name: str) -> None:
    sent, reader = recorded(httpx.Response(200, text=""))
    await READS[name](Analytics(URL, KEY, reader=reader))
    assert sent, "the read asked ClickHouse"
    for request in sent:
        params = request.url.params
        # The row policy's setting, and the query's own filter, each a parameter, never text.
        assert params[TENANT_SETTING] == "acme"
        assert params["param_tenant"] == "acme"
        query = request.content.decode()
        assert "WHERE tenant_id = {tenant:String}" in query
        assert "acme" not in query


async def test_counts_are_read_by_event() -> None:
    rows = '{"event":"member.invited.v1","count":3,"people":2}\n'
    sent, reader = recorded(httpx.Response(200, text=rows))
    counts = await Analytics(URL, KEY, reader=reader).counts(ACME, SPAN)
    assert isinstance(counts, Ok)
    assert [(c.event, c.count, c.people) for c in counts.data] == [("member.invited.v1", 3, 2)]
    assert sent[0].url.params["param_start"] == "2026-10-01 00:00:00.000"
    assert sent[0].url.params["param_end"] == "2026-10-22 00:00:00.000"


async def test_a_read_clickhouse_refuses_or_doesnt_answer_is_unavailable() -> None:
    _, refusing = recorded(httpx.Response(500))
    assert await Analytics(URL, KEY, reader=refusing).counts(ACME, SPAN) == Unavailable(
        reason="ClickHouse answered 500"
    )
    assert await Analytics(URL, KEY, reader=failing()).counts(ACME, SPAN) == Unavailable(
        reason="ClickHouse didn't answer: ConnectError"
    )


async def test_an_event_is_the_servers_with_only_the_registrys_keys() -> None:
    sent, writer = recorded(httpx.Response(200))
    analytics = Analytics(URL, KEY, writer=writer)
    written = await analytics.capture(
        "acme",
        "member.invited.v1",
        "user-1",
        workspace="w1",
        trace_id="0af7651916cd43dd8448eb211c80319c",
        props={"outcome": "invited", "email": "a@example.com"},
    )
    assert written
    (request,) = sent
    assert request.url.params["query"] == "INSERT INTO analytics.events FORMAT JSONEachRow"
    row = json.loads(request.content)
    assert row["tenant_id"] == "acme"
    assert row["workspace_id"] == "w1"
    assert row["event"] == "member.invited.v1"
    assert row["actor_kind"] == "user"
    assert row["props"] == {"outcome": "invited"}
    assert row["distinct_id"] == distinct_id(KEY, "user-1")
    assert "user-1" not in request.content.decode()
    assert "a@example.com" not in request.content.decode()


def test_a_person_is_a_keyed_hash_of_32_hex_digits() -> None:
    once = distinct_id(KEY, "user-1")
    assert len(once) == 32
    assert int(once, 16) >= 0
    assert distinct_id(KEY, "user-1") == once
    assert distinct_id(b"another deployment's key", "user-1") != once


async def test_an_event_not_in_the_registry_is_the_codes_mistake() -> None:
    _, writer = recorded(httpx.Response(200))
    with pytest.raises(ValueError, match="isn't in portalr's analytics registry"):
        await Analytics(URL, KEY, writer=writer).capture("acme", "app.made.up.v1", "user-1")


@pytest.mark.parametrize("answer", ["refused", "unreachable"])
async def test_a_write_that_fails_is_logged_and_dropped(
    answer: str, caplog: pytest.LogCaptureFixture
) -> None:
    if answer == "refused":
        _, writer = recorded(httpx.Response(503))
    else:
        writer = failing()
    with caplog.at_level(logging.WARNING, logger="portalr.analytics"):
        written = await Analytics(URL, KEY, writer=writer).capture(
            "acme", "member.invited.v1", "user-1"
        )
    assert not written
    assert "member.invited.v1 not recorded" in caplog.text
    assert "user-1" not in caplog.text


def test_the_registry_names_each_event_with_its_version() -> None:
    assert REGISTRY
    for name in REGISTRY:
        assert name.rsplit(".", 1)[-1].startswith("v"), name


def test_config_says_whether_analytics_is_configured() -> None:
    assert Readers().configured()["analytics"] is False
    assert Readers(analytics=Analytics(URL, KEY)).configured()["analytics"] is True


def test_the_key_isnt_in_the_readers_repr() -> None:
    assert "deployment's key" not in repr(Analytics(URL, KEY))


async def test_a_span_is_sent_as_utc() -> None:
    sent, reader = recorded(httpx.Response(200, text=""))
    later = datetime(2026, 10, 1, 2, tzinfo=UTC).astimezone(UTC) + timedelta(hours=1)
    await Analytics(URL, KEY, reader=reader).counts(ACME, Span(start=SPAN.start, end=later))
    assert sent[0].url.params["param_end"] == "2026-10-01 03:00:00.000"


def test_an_event_is_by_a_person_or_a_principal_and_no_one_else() -> None:
    assert actor_of(User(id="alice")) == ("user", "alice")
    assert actor_of(ServicePrincipal(id="key-1")) == ("principal", "key-1")
    assert actor_of(Agent()) is None


async def test_a_persons_events_are_recorded_in_one_write_with_their_session() -> None:
    sent, writer = recorded(httpx.Response(200))
    analytics = Analytics(URL, KEY, writer=writer)
    events = [("app.page.viewed.v1", {"route": "/t/$tenant"}), ("app.thread.opened.v1", {})]
    assert await analytics.capture_many("acme", "user-1", events, session_id="s1")
    (request,) = sent
    rows = [json.loads(line) for line in request.content.decode().splitlines()]
    assert [row["event"] for row in rows] == ["app.page.viewed.v1", "app.thread.opened.v1"]
    assert {row["session_id"] for row in rows} == {"s1"}
    assert {row["distinct_id"] for row in rows} == {distinct_id(KEY, "user-1")}


async def test_forgetting_a_person_deletes_their_events_by_their_hash_alone() -> None:
    sent, writer = recorded(httpx.Response(200))
    assert await Analytics(URL, KEY, writer=writer).forget("user-1")
    (request,) = sent
    assert request.content.decode() == (
        "DELETE FROM analytics.events WHERE distinct_id = {person:FixedString(32)}"
    )
    assert request.url.params["param_person"] == distinct_id(KEY, "user-1")
    assert "user-1" not in str(request.url)


async def test_a_deletion_clickhouse_refuses_is_said() -> None:
    _, writer = recorded(httpx.Response(500))
    assert not await Analytics(URL, KEY, writer=writer).forget("user-1")


ANSWERS: dict[str, str] = {
    "uniqExactIf": '{"window":"4","week":"3","month":"4"}',
    "toDate(ts) AS day": '{"day":"2026-10-01","people":"2"}\n{"day":"2026-10-02","people":"1"}',
    "props['integration']": '{"integration":"tracker","uses":"5","people":"2"}',
    "windowFunnel": '{"page":"3","thread":"2","message":"1"}',
    "retention(": '{"retention":["3","2","1"]}',
}
"""Each of the adoption's reads, by what its query selects, in the order they are made."""


def adoption_answers(**overrides: str) -> httpx.AsyncClient:
    """A ClickHouse that answers each of the adoption's reads, by what it selects."""
    answers = {**ANSWERS, **overrides}

    async def handle(request: httpx.Request) -> httpx.Response:
        query = request.content.decode()
        for marker, text in answers.items():
            if marker in query:
                if text == "slow":
                    await asyncio.sleep(1)
                if text == "refused":
                    return httpx.Response(500, text="Code: 241. DB::Exception: secret detail")
                return httpx.Response(200, text=text)
        raise AssertionError(query)

    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


ADOPTION = AdoptionQuery(start=SPAN.start, end=SPAN.end)
"""Three weeks: 21 days."""


async def test_a_tenants_adoption_is_its_people_days_integrations_funnel_and_retention() -> None:
    adoption = await Analytics(URL, KEY, reader=adoption_answers()).adoption(ACME, ADOPTION)
    assert adoption == Ok(
        data=Adoption(
            active=Active(window=4, week=3, month=4),
            days=[
                ActiveDay(day=date(2026, 10, 1), people=2),
                ActiveDay(day=date(2026, 10, 2), people=1),
            ],
            integrations=[IntegrationUse(integration="tracker", uses=5, people=2)],
            funnel=Funnel(page=3, thread=2, message=1),
            retention=[3, 2, 1],
            complete=True,
        )
    )


async def test_retention_asks_after_each_whole_week_of_the_window() -> None:
    sent, reader = recorded(httpx.Response(200, text=""))
    # 30 days: four whole weeks, and two days of a fifth, which isn't asked after.
    window = AdoptionQuery(start=SPAN.start, end=SPAN.start + timedelta(days=30))
    await Analytics(URL, KEY, reader=reader).adoption(ACME, window)
    (asked,) = [r.content.decode() for r in sent if "retention(" in r.content.decode()]
    assert "week = 3)" in asked
    assert "week = 4" not in asked


async def test_a_one_week_window_asks_retention_after_two_weeks_and_keeps_one() -> None:
    window = AdoptionQuery(start=SPAN.start, end=SPAN.start + timedelta(days=7))
    sent: list[str] = []
    answers = adoption_answers(**{"retention(": '{"retention":["3","0"]}'})
    original = answers.post

    async def post(*args: object, **kwargs: object) -> httpx.Response:
        sent.append(str(kwargs["content"]))
        return await original(*args, **kwargs)  # type: ignore[arg-type]

    answers.post = post  # type: ignore[method-assign]
    adoption = await Analytics(URL, KEY, reader=answers).adoption(ACME, window)
    assert isinstance(adoption, Ok)
    assert adoption.data.retention == [3]
    (asked,) = [query for query in sent if "retention(" in query]
    assert "week = 0, week = 1)" in asked


async def test_a_window_shorter_than_a_week_has_no_retention_and_asks_none() -> None:
    sent, reader = recorded(httpx.Response(200, text=""))
    window = AdoptionQuery(start=SPAN.start, end=SPAN.start + timedelta(days=6))
    adoption = await Analytics(URL, KEY, reader=reader).adoption(ACME, window)
    assert isinstance(adoption, Ok)
    assert adoption.data.retention == []
    assert not [r for r in sent if "retention(" in r.content.decode()]


async def test_an_adoption_read_asks_clickhouse_one_query_at_a_time() -> None:
    running, most = 0, 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal running, most
        running += 1
        most = max(most, running)
        await asyncio.sleep(0.01)
        running -= 1
        return httpx.Response(200, text="")

    reader = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    await Analytics(URL, KEY, reader=reader).adoption(ACME, ADOPTION)
    assert most == 1


async def test_an_empty_tenant_has_no_one_and_a_whole_answer() -> None:
    # As ClickHouse answers an aggregate of no rows: zeros, and no days or integrations.
    reader = adoption_answers(
        uniqExactIf='{"window":"0","week":"0","month":"0"}',
        **{
            "toDate(ts) AS day": "",
            "props['integration']": "",
            "windowFunnel": '{"page":"0","thread":"0","message":"0"}',
            "retention(": '{"retention":[]}',
        },
    )
    adoption = await Analytics(URL, KEY, reader=reader).adoption(ACME, ADOPTION)
    assert adoption == Ok(
        data=Adoption(
            active=Active(window=0, week=0, month=0),
            days=[],
            integrations=[],
            funnel=Funnel(page=0, thread=0, message=0),
            retention=[],
            complete=True,
        )
    )


@pytest.mark.parametrize("read", list(ANSWERS))
async def test_a_read_clickhouse_refuses_makes_the_adoption_unavailable_without_its_words(
    read: str,
) -> None:
    reader = adoption_answers(**{read: "refused"})
    adoption = await Analytics(URL, KEY, reader=reader).adoption(ACME, ADOPTION)
    assert adoption == Unavailable(reason="ClickHouse answered 500")


async def test_an_answer_portalr_cant_read_is_unavailable() -> None:
    reader = adoption_answers(uniqExactIf='{"window":"many"}')
    adoption = await Analytics(URL, KEY, reader=reader).adoption(ACME, ADOPTION)
    assert adoption == Unavailable(reason="ClickHouse answered what portalr can't read")


@pytest.mark.parametrize("slow", range(len(ANSWERS)))
async def test_the_parts_not_read_by_the_deadline_are_unknown_not_none(
    slow: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("portalr.readers.analytics.DEADLINE", 0.2)
    reader = adoption_answers(**{list(ANSWERS)[slow]: "slow"})
    adoption = await Analytics(URL, KEY, reader=reader).adoption(ACME, ADOPTION)
    assert isinstance(adoption, Ok)
    parts = ["active", "days", "integrations", "funnel", "retention"]
    read = [getattr(adoption.data, part) is not None for part in parts]
    # Each part before the one the deadline cut off was read; it and each after, not.
    assert read == [n < slow for n in range(len(parts))]
    assert adoption.data.complete is False


def test_an_adoption_window_is_at_most_91_days() -> None:
    with pytest.raises(ValidationError, match="at most 91 days"):
        AdoptionQuery(start=SPAN.start, end=SPAN.start + timedelta(days=92))
