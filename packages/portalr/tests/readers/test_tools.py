"""Loki, Prometheus, Langfuse, LiteLLM and Grafana, each against a stand-in for its API."""

import json as jsonlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx

from portalr.readers import (
    Grafana,
    Langfuse,
    LiteLLM,
    LogQuery,
    Loki,
    MetricQuery,
    Ok,
    Prometheus,
    Spend,
    TenantSpend,
    Unavailable,
    Window,
)
from portalr.tenant import allowed
from tests.tools import Tool, fails, json

ACME = allowed("acme")
START = datetime(2026, 10, 12, tzinfo=UTC)
END = START + timedelta(hours=1)


async def test_loki_reads_the_tenants_logs_newest_first() -> None:
    answer = {
        "data": {
            "result": [
                {
                    "stream": {"service_name": "docplan"},
                    "values": [["1", "first"], ["3", "third", {"tenant_id": "acme"}]],
                },
                {"stream": {"service_name": "oncall"}, "values": [["2", "second"]]},
            ]
        }
    }
    tool = Tool({"/loki/api/v1/query_range": json(answer)})
    logs = await Loki("http://loki", tool.client()).logs(
        ACME, LogQuery(start=START, end=END, limit=2)
    )
    assert isinstance(logs, Ok)
    assert [(line.time_ns, line.line, line.labels["service_name"]) for line in logs.data] == [
        (3, "third", "docplan"),
        (2, "second", "oncall"),
    ]
    params = tool.last.url.params
    assert params["query"] == '{service_name=~".+"} | tenant_id = "acme"'
    assert (params["direction"], params["limit"]) == ("backward", "2")
    assert params["start"] == str(int(START.timestamp()) * 1_000_000_000)


async def test_loki_down_or_absent_is_unavailable() -> None:
    query = LogQuery(start=START, end=END)
    down = Loki("http://loki", Tool({"/loki/api/v1/query_range": json({}, status=503)}).client())
    assert await down.logs(ACME, query) == Unavailable(reason="loki answered 503")
    absent = Loki("http://loki", Tool().client())
    assert await absent.logs(ACME, query) == Unavailable(
        reason="loki has no query API at that address"
    )


async def test_prometheus_reads_a_metric_through_the_proxy_with_the_tenant() -> None:
    answer = {"data": {"result": [{"metric": {}, "values": [[1.5, "0.25"], [2.5, "0.5"]]}]}}
    tool = Tool({"/api/v1/query_range": json(answer)})
    query = MetricQuery(start=START, end=END, metric="failed_runs", step=timedelta(minutes=1))
    series = await Prometheus("http://proxy", tool.client()).series(ACME, query)
    assert isinstance(series, Ok)
    assert [(point.time, point.value) for point in series.data] == [(1.5, 0.25), (2.5, 0.5)]
    assert tool.last.url.params["tenant_id"] == "acme"
    assert tool.last.url.params["step"] == "60.0"


async def test_prometheus_answering_nonsense_or_nothing_is_unavailable() -> None:
    query = MetricQuery(start=START, end=END, metric="turn_latency")
    odd = Prometheus("http://proxy", Tool({"/api/v1/query_range": json({"no": "data"})}).client())
    assert await odd.series(ACME, query) == Unavailable(
        reason="prometheus answered with something unexpected"
    )
    absent = Prometheus("http://proxy", Tool().client())
    assert await absent.series(ACME, query) == Unavailable(
        reason="prometheus has no query API at that address"
    )


async def test_langfuse_reads_the_tenants_scores_newest_first_and_links_for_operators() -> None:
    page = {
        "data": [
            {
                "id": "s1",
                "traceId": "t1",
                "name": "thumbs",
                "value": 1,
                "source": "API",
                "timestamp": "2026-10-12T00:00:00Z",
            },
            {
                "id": "s2",
                "name": "accuracy",
                "stringValue": "good",
                "timestamp": "2026-10-12T01:00:00Z",
                "comment": "fine",
            },
        ]
    }
    tool = Tool({"/api/public/scores": json(page)})
    langfuse = Langfuse("http://langfuse", project="p1", client=tool.client())
    scores = await langfuse.scores(ACME, Window(start=START, end=END))
    assert isinstance(scores, Ok)
    assert [score.id for score in scores.data] == ["s2", "s1"]
    assert tool.last.url.params["traceTags"] == "tenant:acme"
    assert langfuse.trace_link("t1") == "http://langfuse/project/p1/traces/t1"
    assert langfuse.session_link("thr_1") == "http://langfuse/project/p1/sessions/thr_1"
    absent = Langfuse("http://langfuse", project="p1", client=Tool().client())
    assert await absent.scores(ACME, Window(start=START, end=END)) == Unavailable(
        reason="langfuse has no scores API at that address"
    )


async def test_litellm_reads_the_tenants_team_and_every_tenant_for_operators() -> None:
    info = {
        "team_info": {
            "team_id": "tenant-acme",
            "spend": 4.5,
            "max_budget": 10,
            "budget_duration": "30d",
        }
    }
    teams = [
        {"team_id": "tenant-acme", "spend": 4.5},
        {"team_id": "tenant-globex", "spend": 1},
        {"team_id": "ops", "spend": 9},
    ]
    tool = Tool({"/team/info": json(info), "/team/list": json(teams)})
    litellm = LiteLLM("http://litellm", tool.client())
    assert await litellm.spend(ACME) == Ok(
        data=Spend(spend=4.5, max_budget=10, budget_duration="30d")
    )
    assert tool.last.url.params["team_id"] == "tenant-acme"
    assert await litellm.every_tenant() == Ok(
        data=[TenantSpend(tenant="acme", spend=4.5), TenantSpend(tenant="globex", spend=1)]
    )


async def test_litellm_without_the_team_or_down() -> None:
    assert await LiteLLM("http://litellm", Tool().client()).spend(ACME) == Ok(data=None)
    assert await LiteLLM("http://litellm", Tool().client()).every_tenant() == Unavailable(
        reason="litellm has no team list at that address"
    )
    down = LiteLLM("http://litellm", Tool({"/team/info": fails(httpx.ConnectTimeout)}).client())
    assert await down.spend(ACME) == Unavailable(reason="litellm didn't answer: ConnectTimeout")


def test_grafana_links_into_explore() -> None:
    grafana = Grafana("http://grafana")
    trace = parse_qs(urlparse(grafana.trace_link("t1")).query)["left"][0]
    assert jsonlib.loads(trace) == {
        "datasource": "tempo",
        "queries": [{"refId": "A", "queryType": "traceql", "query": "t1"}],
    }
    logs = parse_qs(urlparse(grafana.run_logs_link("run_1")).query)["left"][0]
    assert jsonlib.loads(logs)["queries"][0]["expr"] == (
        '{service_name=~".+"} | artifactr_run_id = "run_1" or reflexr_run_id = "run_1"'
    )
