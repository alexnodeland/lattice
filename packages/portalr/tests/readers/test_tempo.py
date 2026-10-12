from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from portalr.readers import Ok, Tempo, TraceQuery, Unavailable
from portalr.tenant import allowed
from tests.tools import Tool, fails, json

ACME = allowed("acme")
START = datetime(2026, 10, 12, tzinfo=UTC)
QUERY = TraceQuery(start=START, end=START + timedelta(hours=1), session="thr_1", limit=5)


def span(
    span_id: str, tenant: str | None, *, parent: str = "", error: bool = False
) -> dict[str, Any]:
    attributes: list[dict[str, Any]] = [
        {"key": "artifactr.run.id", "value": {"stringValue": "run_1"}},
        {"key": "retries", "value": {"intValue": "2"}},
        {"key": "cached", "value": {"boolValue": True}},
        {"key": "score", "value": {"doubleValue": 0.5}},
        {"key": "empty", "value": {}},
    ]
    if tenant:
        attributes.append({"key": "tenant.id", "value": {"stringValue": tenant}})
    return {
        "spanId": span_id,
        "parentSpanId": parent,
        "name": f"span {span_id}",
        "startTimeUnixNano": "1000",
        "endTimeUnixNano": "2000",
        "attributes": attributes,
        "status": {"code": "STATUS_CODE_ERROR"} if error else {},
    }


def document(*spans: dict[str, Any]) -> dict[str, Any]:
    return {"trace": {"resourceSpans": [{"scopeSpans": [{"spans": list(spans)}]}]}}


async def test_a_search_sends_the_tenants_traceql_and_answers_newest_first() -> None:
    found = {
        "traces": [
            {
                "traceID": "a",
                "rootServiceName": "docplan",
                "rootTraceName": "turn",
                "startTimeUnixNano": "1",
                "durationMs": 3,
            },
            {"traceID": "b", "startTimeUnixNano": "2"},
        ]
    }
    tool = Tool({"/api/search": json(found)})
    answer = await Tempo("http://tempo", tool.client()).search(ACME, QUERY)
    assert isinstance(answer, Ok)
    assert [trace.trace_id for trace in answer.data] == ["b", "a"]
    # The root may be another tenant's span: its service and name aren't shown.
    assert [(trace.root_service, trace.root_name, trace.duration_ms) for trace in answer.data] == [
        (None, None, None),
        (None, None, 3),
    ]
    params = tool.last.url.params
    assert params["q"] == '{ span.tenant.id = "acme" && span.session.id = "thr_1" }'
    assert (params["start"], params["end"], params["limit"]) == (
        str(int(QUERY.start.timestamp())),
        str(int(QUERY.end.timestamp())),
        "5",
    )


async def test_a_trace_is_shown_when_a_span_names_the_tenant_and_none_names_another() -> None:
    tool = Tool(
        {
            "/api/v2/traces/t1": json(
                document(span("1", "acme"), span("2", None, parent="1", error=True))
            )
        }
    )
    answer = await Tempo("http://tempo", tool.client()).trace(ACME, "t1")
    assert isinstance(answer, Ok)
    assert answer.data is not None
    root, child = answer.data.spans
    assert (root.parent_id, child.parent_id, child.error, root.error) == (None, "1", True, False)
    assert root.attributes == {
        "artifactr.run.id": "run_1",
        "retries": 2,
        "cached": True,
        "score": 0.5,
        "empty": 0,
        "tenant.id": "acme",
    }


async def test_a_trace_that_names_another_tenant_or_none_isnt_shown() -> None:
    for spans in [
        (span("1", "acme"), span("2", "globex")),
        (span("1", "globex"),),
        (span("1", None),),
    ]:
        tool = Tool({"/api/v2/traces/t1": json(document(*spans))})
        assert await Tempo("http://tempo", tool.client()).trace(ACME, "t1") == Ok(data=None)


async def test_a_missing_trace_is_none() -> None:
    assert await Tempo("http://tempo", Tool().client()).trace(ACME, "t1") == Ok(data=None)


async def test_tempo_down_is_unavailable() -> None:
    tempo = Tempo(
        "http://tempo",
        Tool({"/api/search": fails(), "/api/v2/traces/t1": fails(httpx.ReadTimeout)}).client(),
    )
    assert await tempo.search(ACME, QUERY) == Unavailable(
        reason="tempo didn't answer: ConnectError"
    )
    assert await tempo.trace(ACME, "t1") == Unavailable(reason="tempo didn't answer: ReadTimeout")
    assert await Tempo("http://tempo", Tool().client()).search(ACME, QUERY) == Unavailable(
        reason="tempo has no search API at that address"
    )
