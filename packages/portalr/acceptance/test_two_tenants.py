"""portalr's readers against a stack seeded with two tenants: reading as one never sees the other.

``moon run portalr:api`` starts Tempo, Loki, Prometheus and prom-label-proxy, and runs this with
their URLs. Each test waits for what it reads to arrive, as the tools take a moment to index it.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from acceptance.seed import RUN, seed
from portalr.readers import LogQuery, Loki, MetricQuery, Ok, Prometheus, Tempo, TraceQuery
from portalr.tenant import allowed

ACME, GLOBEX = allowed("acme"), allowed("globex")
START, END = datetime.now(UTC) - timedelta(hours=1), datetime.now(UTC) + timedelta(minutes=5)


def url(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.fail(f"{name} is unset: run these through portalr's api task")
    return value


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture(scope="module")
def ids() -> dict[str, str]:
    return seed(url("PORTALR_TEMPO_OTLP"), url("PORTALR_LOKI_URL"), url("PORTALR_PROMETHEUS_URL"))


async def eventually[T](read: Callable[[], Awaitable[T]], ready: Callable[[T], bool]) -> T:
    """Read until the answer is ready, for up to a minute."""
    answer = await read()
    for _ in range(60):
        if ready(answer):
            return answer
        await asyncio.sleep(1)
        answer = await read()
    raise AssertionError(f"never ready: {answer}")


async def test_tempo_finds_a_tenants_traces_and_shows_none_another_shares(
    ids: dict[str, str], client: httpx.AsyncClient
) -> None:
    tempo = Tempo(url("PORTALR_TEMPO_URL"), client)
    query = TraceQuery(start=START, end=END, limit=100)

    def found(answer: object) -> set[str]:
        return {trace.trace_id for trace in answer.data} if isinstance(answer, Ok) else set()

    acme = await eventually(
        lambda: tempo.search(ACME, query), lambda a: {ids["acme"], ids["mixed"]} <= found(a)
    )
    assert ids["globex"] not in found(acme)
    globex = await eventually(
        lambda: tempo.search(GLOBEX, query), lambda a: ids["globex"] in found(a)
    )
    assert ids["acme"] not in found(globex)
    # A trace both tenants' spans share is found by its acme span, and shown to neither.
    assert await tempo.trace(ACME, ids["mixed"]) == Ok(data=None)
    assert await tempo.trace(GLOBEX, ids["mixed"]) == Ok(data=None)
    assert await tempo.trace(GLOBEX, ids["acme"]) == Ok(data=None)
    mine = await tempo.trace(ACME, ids["acme"])
    assert isinstance(mine, Ok)
    assert mine.data is not None
    assert {span.attributes["tenant.id"] for span in mine.data.spans} == {"acme"}


async def test_loki_reads_a_tenants_logs_only(
    ids: dict[str, str], client: httpx.AsyncClient
) -> None:
    del ids  # seeded
    loki = Loki(url("PORTALR_LOKI_URL"), client)
    query = LogQuery(start=START, end=END, limit=1000)

    def lines(answer: object) -> list[str]:
        return (
            [line.line for line in answer.data if RUN in line.line]
            if isinstance(answer, Ok)
            else []
        )

    acme = await eventually(lambda: loki.logs(ACME, query), lambda a: bool(lines(a)))
    assert lines(acme) == [f"acme's record {RUN}"]
    globex = await eventually(lambda: loki.logs(GLOBEX, query), lambda a: bool(lines(a)))
    assert lines(globex) == [f"globex's record {RUN}"]


async def test_prometheus_through_the_proxy_reads_a_tenants_series_only(
    ids: dict[str, str], client: httpx.AsyncClient
) -> None:
    del ids  # seeded
    proxied = Prometheus(url("PORTALR_PROXY_URL"), client)
    query = MetricQuery(start=START, end=END, metric="failed_runs", step=timedelta(minutes=1))

    def peak(answer: object) -> float:
        return (
            max((point.value for point in answer.data), default=0) if isinstance(answer, Ok) else 0
        )

    acme = await eventually(lambda: proxied.series(ACME, query), lambda a: peak(a) > 0)
    globex = await eventually(lambda: proxied.series(GLOBEX, query), lambda a: peak(a) > 0)
    # acme fails once a minute, and globex a hundred times: neither's rate holds the other's.
    assert peak(acme) < 0.1 < 1 < peak(globex)
