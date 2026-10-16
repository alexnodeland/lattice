"""Loki, Prometheus, Langfuse, LiteLLM and Grafana, each against a stand-in for its API."""

import asyncio
import json as jsonlib
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from pydantic import ValidationError

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
from portalr.readers.langfuse import Scores, workspace_of
from portalr.readers.loki import _record
from portalr.tenant import allowed
from tests.tools import Tool, fails, json

ACME = allowed("acme")
START = datetime(2026, 10, 12, tzinfo=UTC)
END = START + timedelta(hours=1)
AT = "2026-10-12T00:00:00Z"


ME = {"tenant_id": "acme"}


def stream(labels: dict[str, str], *values: list[str | dict[str, str]]) -> dict[str, object]:
    return {"stream": {**ME, **labels}, "values": list(values)}


async def test_loki_reads_the_tenants_logs_newest_first_without_their_lines() -> None:
    answer = {
        "data": {
            "result": [
                stream({"service_name": "docplan"}, ["1", "first"], ["3", "third", {"x": "y"}]),
                stream(
                    {
                        "service_name": "oncall",
                        "detected_level": "error",
                        "artifactr_thread_id": "thr_1",
                        "reflexr_run_id": "run_9",
                        "extra_thing": "x",
                        "email": "a@b.c",
                    },
                    ["2", "second line"],
                ),
            ]
        }
    }
    tool = Tool({"/loki/api/v1/query_range": json(answer)})
    logs = await Loki("http://loki", tool.client()).logs(
        ACME, LogQuery(start=START, end=END, limit=4)
    )
    assert isinstance(logs, Ok)
    assert [(record.time_ns, record.service, record.length) for record in logs.data.records] == [
        (3, "docplan", 5),
        (2, "oncall", 11),
        (1, "docplan", 5),
    ]
    second = logs.data.records[1]
    # What is known to be safe is shown; the rest is named, and the line isn't there at all.
    assert (second.level, second.thread, second.run) == ("error", "thr_1", "run_9")
    assert second.withheld == ("email", "extra_thing")
    assert "email" not in second.labels
    assert "extra_thing" not in second.labels
    assert second.line is None
    assert "second line" not in logs.model_dump_json()
    assert logs.data.complete
    params = tool.last.url.params
    assert params["query"] == '{service_name=~".+"} | tenant_id = "acme"'
    assert (params["direction"], params["limit"]) == ("backward", "4")
    assert params["start"] == str(int(START.timestamp()) * 1_000_000_000)


async def test_a_record_that_isnt_the_tenants_is_never_shown_whatever_loki_says() -> None:
    answer = {
        "data": {
            "result": [
                stream({"service_name": "a"}, ["3", "mine"]),
                {
                    "stream": {"tenant_id": "globex", "service_name": "b"},
                    "values": [["2", "theirs"]],
                },
                {"stream": {"service_name": "c"}, "values": [["1", "nobody's"]]},
            ]
        }
    }
    tool = Tool({"/loki/api/v1/query_range": json(answer)})
    logs = await Loki("http://loki", tool.client()).logs(ACME, LogQuery(start=START, end=END))
    assert isinstance(logs, Ok)
    assert [record.time_ns for record in logs.data.records] == [3]
    assert "theirs" not in logs.model_dump_json()


async def test_a_read_that_filled_its_limit_says_it_may_have_more() -> None:
    answer = {"data": {"result": [stream({}, ["1", "a"], ["2", "b"])]}}
    tool = Tool({"/loki/api/v1/query_range": json(answer)})
    logs = await Loki("http://loki", tool.client()).logs(
        ACME, LogQuery(start=START, end=END, limit=2)
    )
    assert isinstance(logs, Ok)
    assert not logs.data.complete
    more = await Loki("http://loki", tool.client()).logs(
        ACME, LogQuery(start=START, end=END, limit=3)
    )
    assert isinstance(more, Ok)
    assert more.data.complete


def test_a_window_is_a_day_at_most() -> None:
    assert LogQuery(start=START, end=START + timedelta(hours=24)).end
    with pytest.raises(ValidationError, match="at most 24 hours"):
        LogQuery(start=START, end=START + timedelta(hours=24, seconds=1))


async def test_a_record_is_read_by_its_id_with_its_line_and_by_no_other() -> None:
    labels = {"service_name": "docplan", "artifactr_run_id": "run_1", "email": "a@b.c"}
    answer = {
        "data": {
            "result": [
                stream(labels, ["5", "this one"]),
                stream({"service_name": "other"}, ["5", "the same instant"]),
            ]
        }
    }
    tool = Tool({"/loki/api/v1/query_range": json(answer)})
    loki = Loki("http://loki", tool.client())
    listed = await loki.logs(ACME, LogQuery(start=START, end=END))
    assert isinstance(listed, Ok)
    first, second = sorted(listed.data.records, key=lambda record: record.service or "")
    assert first.id != second.id
    assert re.fullmatch(r"5-[0-9a-f]{16}", first.id)
    # `first` is docplan's, which has the email label to withhold.
    one = await loki.record(ACME, first.id)
    assert isinstance(one, Ok)
    assert one.data is not None
    assert (one.data.line, one.data.withheld) == ("this one", ("email",))
    # It looked at that instant alone, for the tenant alone.
    params = tool.last.url.params
    assert (params["start"], params["end"]) == ("5", "6")
    assert params["query"] == '{service_name=~".+"} | tenant_id = "acme"'
    # An id that names no record, another's digest, or no id at all, is none.
    for record_id in (f"5-{'0' * 16}", f"6-{first.id.split('-')[1]}", "5", "x-y", "", "5-ABC"):
        assert await loki.record(ACME, record_id) == Ok(data=None), record_id


async def test_another_tenants_record_is_not_found_by_its_id() -> None:
    theirs = {"stream": {"tenant_id": "globex", "service_name": "b"}, "values": [["5", "theirs"]]}
    tool = Tool({"/loki/api/v1/query_range": json({"data": {"result": [theirs]}})})
    loki = Loki("http://loki", tool.client())
    mine = Loki(
        "http://loki", Tool({"/loki/api/v1/query_range": json({"data": {"result": []}})}).client()
    )
    # The id a record of globex's has, asked for as acme: Loki, here wrong, answers it anyway.
    globex_id = _record(5, "theirs", {"tenant_id": "globex", "service_name": "b"}).id
    assert await loki.record(ACME, globex_id) == Ok(data=None)
    assert await mine.record(ACME, globex_id) == Ok(data=None)


async def test_loki_down_slow_or_absent_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    query = LogQuery(start=START, end=END)
    down = Loki("http://loki", Tool({"/loki/api/v1/query_range": json({}, status=503)}).client())
    assert await down.logs(ACME, query) == Unavailable(reason="loki answered 503")
    assert await down.record(ACME, "5-" + "a" * 16) == Unavailable(reason="loki answered 503")
    absent = Loki("http://loki", Tool().client())
    assert await absent.logs(ACME, query) == Unavailable(
        reason="loki has no query API at that address"
    )
    monkeypatch.setattr("portalr.readers.loki.DEADLINE", 0.05)

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    waiting = Loki("http://loki", httpx.AsyncClient(transport=httpx.MockTransport(slow)))
    assert await waiting.logs(ACME, query) == Unavailable(reason="loki didn't answer in time")


async def test_prometheus_reads_a_metric_through_the_proxy_with_the_tenant() -> None:
    answer = {"data": {"result": [{"metric": {}, "values": [[1.5, "0.25"], [2.5, "0.5"]]}]}}
    tool = Tool({"/api/v1/query_range": json(answer)})
    query = MetricQuery(start=START, end=END, metric="failed_turns", step=60)
    series = await Prometheus("http://proxy", tool.client()).series(ACME, query)
    assert isinstance(series, Ok)
    assert [(point.time, point.value) for point in series.data] == [(1.5, 0.25), (2.5, 0.5)]
    assert tool.last.url.params["tenant_id"] == "acme"
    assert tool.last.url.params["step"] == "60"
    assert tool.last.url.params["query"] == (
        'sum(increase(artifactr_turns_total{artifactr_turn_outcome="failed",tenant_id="acme"}[60s]))'
    ), "each point counts the failures in the step before it"


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
    observations = {
        "data": [
            {"traceId": "t1", "startTime": AT, "tags": ["tenant:acme"]},
            {
                "traceId": "t2",
                "startTime": AT,
                "tags": ["tenant:acme", "thread:thr_1", "workspace:notes"],
            },
            # Langfuse ignored the filter: another tenant's trace is left out.
            {"traceId": "t3", "startTime": AT, "tags": ["tenant:globex"]},
        ]
    }
    scores = {
        "data": [
            {
                "id": "s1",
                "name": "thumbs",
                "dataType": "BOOLEAN",
                "value": True,
                "source": "API",
                "timestamp": "2026-10-12T00:00:00Z",
                "subject": {"kind": "trace", "id": "t1"},
                "metadata": {"tenant": "acme", "person": "alice", "feedback_type": "thumbs"},
            },
            {
                "id": "s2",
                "name": "accuracy",
                "dataType": "CATEGORICAL",
                "value": "good",
                "source": "EVAL",
                "timestamp": "2026-10-12T01:00:00Z",
                "comment": "fine",
                "subject": {"kind": "observation", "id": "o1", "traceId": "t2"},
                "metadata": {"evaluator": "accuracy", "version": "1"},
            },
            # On a trace that isn't the tenant's, or on no trace: dropped.
            {
                "id": "s3",
                "name": "thumbs",
                "dataType": "NUMERIC",
                "value": 0,
                "source": "API",
                "timestamp": "2026-10-12T02:00:00Z",
                "subject": {"kind": "trace", "id": "t3"},
            },
            {
                "id": "s4",
                "name": "thumbs",
                "dataType": "NUMERIC",
                "value": 1,
                "source": "API",
                "timestamp": "2026-10-12T03:00:00Z",
                "subject": {"kind": "session", "id": "thr_1"},
            },
            {
                "id": "s5",
                "name": "thumbs",
                "dataType": "NUMERIC",
                "value": 1,
                "source": "API",
                "timestamp": "2026-10-12T04:00:00Z",
            },
        ]
    }
    tool = Tool(
        {"/api/public/v2/observations": json(observations), "/api/public/v3/scores": json(scores)}
    )
    langfuse = Langfuse("http://langfuse", project="p1", client=tool.client())
    read = await langfuse.scores(ACME, Window(start=START, end=END))
    assert isinstance(read, Ok)
    assert read.data.complete
    assert [(score.id, score.trace_id, score.value) for score in read.data.scores] == [
        ("s2", "t2", "good"),
        ("s1", "t1", True),
    ]
    # evalr names its evaluator in the metadata; a person's feedback names none.
    assert [score.evaluator for score in read.data.scores] == ["accuracy", None]
    # The mirrors name a person's feedback type in it.
    assert [score.feedback_type for score in read.data.scores] == [None, "thumbs"]
    # A trace's workspace tag names its scores' workspace; a trace with none, none.
    assert [score.workspace for score in read.data.scores] == ["notes", None]
    assert tool.last.url.params["traceId"] == "t1,t2"
    assert langfuse.trace_link("t1") == "http://langfuse/project/p1/traces/t1"
    assert langfuse.session_link("thr_1") == "http://langfuse/project/p1/sessions/thr_1"


async def test_langfuse_names_at_most_fifty_traces_a_request() -> None:
    observations = {
        "data": [
            {"traceId": f"t{n:03}", "startTime": AT, "tags": ["tenant:acme"]} for n in range(120)
        ]
    }
    tool = Tool(
        {
            "/api/public/v2/observations": json(observations),
            "/api/public/v3/scores": json({"data": []}),
        }
    )
    langfuse = Langfuse("http://langfuse", project="p1", client=tool.client())
    assert await langfuse.scores(ACME, Window(start=START, end=END)) == Ok(
        data=Scores(scores=[], complete=True)
    )
    named = [request.url.params["traceId"].split(",") for request in tool.requests[1:]]
    # Asked a few at a time, so in any order.
    assert sorted(len(traces) for traces in named) == [20, 50, 50]


async def test_langfuse_without_its_apis_or_tags_is_unavailable() -> None:
    absent = Langfuse("http://langfuse", project="p1", client=Tool().client())
    assert await absent.scores(ACME, Window(start=START, end=END)) == Unavailable(
        reason="langfuse has no observations API at that address"
    )
    traced = {
        "/api/public/v2/observations": json(
            {"data": [{"traceId": "t1", "startTime": AT, "tags": ["tenant:acme"]}]}
        )
    }
    no_scores = Langfuse("http://langfuse", project="p1", client=Tool(traced).client())
    assert await no_scores.scores(ACME, Window(start=START, end=END)) == Unavailable(
        reason="langfuse has no scores API at that address"
    )
    untagged = {"/api/public/v2/observations": json({"data": [{"traceId": "t1", "startTime": AT}]})}
    langfuse = Langfuse("http://langfuse", project="p1", client=Tool(untagged).client())
    assert await langfuse.scores(ACME, Window(start=START, end=END)) == Unavailable(
        reason="langfuse answered observations without their traces' tags"
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


async def test_litellm_answering_with_another_team_is_unavailable() -> None:
    info = {"team_info": {"team_id": "tenant-globex", "spend": 9}}
    litellm = LiteLLM("http://litellm", Tool({"/team/info": json(info)}).client())
    assert await litellm.spend(ACME) == Unavailable(reason="litellm answered with another team")


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


def test_a_trace_names_one_workspace_or_none() -> None:
    assert workspace_of(["tenant:acme", "workspace:notes"]) == "notes"
    assert workspace_of(["tenant:acme"]) is None
    assert workspace_of(["workspace:notes", "workspace:plans"]) is None
    assert workspace_of(["workspace:notes", "workspace:notes"]) == "notes"


async def test_a_quantile_of_nothing_is_a_gap_not_a_number() -> None:
    answer = {
        "data": {
            "result": [{"metric": {}, "values": [[1, "NaN"], [2, "0.5"], [3, "+Inf"], [4, "2"]]}]
        }
    }
    tool = Tool({"/api/v1/query_range": json(answer)})
    read = await Prometheus("http://proxy", tool.client()).series(
        ACME, MetricQuery(start=START, end=END, metric="turn_latency")
    )
    assert isinstance(read, Ok)
    assert [(point.time, point.value) for point in read.data] == [(2, 0.5), (4, 2.0)]
