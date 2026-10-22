"""portalr's analytics: each event is the registry's and the server's; each read, the tenant's."""

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from grantr.core import Agent, ServicePrincipal, User
from portalr.readers import Analytics, Readers
from portalr.readers.analytics import REGISTRY, TENANT_SETTING, actor_of, distinct_id
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
}
"""Every read the analytics reader has: a new one is added here, and held to the tenant below."""


def test_every_read_of_the_reader_is_listed() -> None:
    public = {name for name in vars(Analytics) if not name.startswith("_")}
    assert public - {"capture", "url", "key", "writer", "reader"} == set(READS)


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
