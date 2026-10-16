import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from portalr.readers import Ok, Tempo, TraceQuery, Unavailable
from portalr.readers.tempo import Span, _padded, _without_repeats
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
        # The values a span may hold, under a name known to be safe: a family of counts.
        {"key": "gen_ai.usage.retries", "value": {"intValue": "2"}},
        {"key": "gen_ai.usage.cached", "value": {"intValue": "3"}},
        {"key": "gen_ai.usage.score", "value": {"doubleValue": 0.5}},
        {"key": "gen_ai.usage.empty", "value": {}},
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
    assert [trace.trace_id for trace in answer.data] == ["0" * 31 + "b", "0" * 31 + "a"]
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
        "gen_ai.usage.retries": 2,
        "gen_ai.usage.cached": 3,
        "gen_ai.usage.score": 0.5,
        "gen_ai.usage.empty": 0,
        "tenant.id": "acme",
    }


def said(span_id: str, tenant: str, content: dict[str, str]) -> dict[str, Any]:
    made = span(span_id, tenant)
    made["attributes"] += [
        {"key": name, "value": {"stringValue": value}} for name, value in content.items()
    ]
    return made


# What a trace may hold that a person or a model said, or that a library or a version may add:
# none of it is on the list of what is known to be safe.
CONTENT = {
    "gen_ai.input.messages": "[prompt]",
    "gen_ai.output.messages": "[completion]",
    "gen_ai.system_instructions": "[instructions]",
    "gen_ai.tool.call.arguments": "{args}",
    "gen_ai.tool.call.result": "{result}",
    "gen_ai.prompt": "old prompt",
    "gen_ai.completion": "old completion",
    "pydantic_ai.all_messages": "[all]",
    "pydantic_ai.all_messages_events": "[events]",
    "final_result": "result",
    "tool_arguments": "{a}",
    "tool_response": "{r}",
    "http.request.body": "secret=1",
    "http.response.body": "token",
    "db.statement": "select 1",
    "db.query.text": "select 2",
    "exception.message": "Bearer abc",
    "logfire.msg": "said something",
    "artifactr.run.reason": "because",
    "some.library.newly_added": "who knows",
}


async def test_a_trace_shows_only_what_is_known_to_be_safe_and_names_the_rest() -> None:
    chat = said("1", "acme", CONTENT | {"gen_ai.usage.prompt": "text, not a count"})
    chat["attributes"].append({"key": "gen_ai.usage.input_tokens", "value": {"intValue": "5"}})
    chat["attributes"].append({"key": "gen_ai.usage.flag", "value": {"boolValue": True}})
    chat["attributes"].append({"key": "gen_ai.usage.cost", "value": {"doubleValue": 0.25}})
    tool = Tool({"/api/v2/traces/f1": json(document(chat))})
    answer = await Tempo("http://tempo", tool.client()).trace(ACME, "f1")
    assert isinstance(answer, Ok)
    assert answer.data is not None
    (shown,) = answer.data.spans
    # A family of counts shows numbers alone: a crafted name carrying text, or a flag, doesn't.
    assert shown.withheld == tuple(sorted([*CONTENT, "gen_ai.usage.flag", "gen_ai.usage.prompt"]))
    for name in CONTENT:
        assert name not in shown.attributes, name
    # What is known to be safe is shown: ids, counts, and a family of usage counts.
    assert shown.attributes["gen_ai.usage.input_tokens"] == 5
    assert shown.attributes["gen_ai.usage.cost"] == 0.25
    assert shown.attributes["artifactr.run.id"] == "run_1"
    assert shown.attributes["tenant.id"] == "acme"
    # Nothing of what was withheld is anywhere in the answer.
    assert "[prompt]" not in answer.model_dump_json()
    assert "Bearer abc" not in answer.model_dump_json()


async def test_only_the_span_asked_for_gives_what_it_withheld() -> None:
    first = said("1", "acme", {"gen_ai.input.messages": "[one]"})
    second = said("2", "acme", {"gen_ai.input.messages": "[two]"})
    tool = Tool({"/api/v2/traces/f1": json(document(first, second))})
    answer = await Tempo("http://tempo", tool.client()).trace(ACME, "f1", reveal="2")
    assert isinstance(answer, Ok)
    assert answer.data is not None
    one, two = answer.data.spans
    assert (one.withheld, "gen_ai.input.messages" in one.attributes) == (
        ("gen_ai.input.messages",),
        False,
    )
    assert (two.withheld, two.attributes["gen_ai.input.messages"]) == ((), "[two]")
    assert "[one]" not in answer.model_dump_json()
    # A span that isn't in the trace reveals nothing.
    none = await Tempo("http://tempo", tool.client()).trace(ACME, "f1", reveal="9")
    assert isinstance(none, Ok)
    assert none.data is not None
    assert all(each.withheld for each in none.data.spans)


async def test_a_span_asked_for_in_another_tenants_trace_is_still_none() -> None:
    for spans in [
        (said("1", "acme", CONTENT), span("2", "globex")),
        (said("1", "globex", CONTENT),),
        # Another tenant's span that reuses an id isn't a repeat to be dropped before it is seen.
        (span("1", "acme"), span("1", "globex")),
        (span("1", "globex"), span("1", "acme")),
    ]:
        tool = Tool({"/api/v2/traces/f1": json(document(*spans))})
        assert await Tempo("http://tempo", tool.client()).trace(ACME, "f1", reveal="1") == Ok(
            data=None
        )


async def test_spans_ids_are_hex_whether_tempo_gives_them_in_hex_or_base64() -> None:
    root, child = "g9tvy+jIHbo=", "A1B2c3D4e5F60718"
    document_ = document(
        {**span(root, "acme"), "spanId": root},
        {**span("c", None), "spanId": child, "parentSpanId": root},
        {**span("d", None), "spanId": "not base64!", "parentSpanId": "AAAA"},
    )
    tool = Tool({"/api/v2/traces/f1": json(document_)})
    answer = await Tempo("http://tempo", tool.client()).trace(ACME, "f1")
    assert isinstance(answer, Ok)
    assert answer.data is not None
    first, second, third = answer.data.spans
    assert first.span_id == "83db6fcbe8c81dba"
    assert (second.span_id, second.parent_id) == ("a1b2c3d4e5f60718", "83db6fcbe8c81dba")
    # What isn't an id is left as it came.
    assert (third.span_id, third.parent_id) == ("not base64!", "AAAA")


async def test_a_trace_past_the_most_spans_says_so_and_a_slow_tempo_is_unavailable(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr("portalr.readers.tempo.MOST_SPANS", 2)
    spans = (span("1", "acme"), span("2", None, parent="1"), span("3", None, parent="1"))
    tool = Tool({"/api/v2/traces/f1": json(document(*spans))})
    answer = await Tempo("http://tempo", tool.client()).trace(ACME, "f1")
    assert isinstance(answer, Ok)
    assert answer.data is not None
    assert [each.span_id for each in answer.data.spans] == ["1", "2"]
    assert not answer.data.complete
    # Whose it is is settled over every span, those past the cap too.
    other = (span("1", "acme"), span("2", None), span("3", "globex"))
    tool = Tool({"/api/v2/traces/f1": json(document(*other))})
    assert await Tempo("http://tempo", tool.client()).trace(ACME, "f1") == Ok(data=None)
    monkeypatch.setattr("portalr.readers.tempo.DEADLINE", 0.05)

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    waiting = Tempo("http://tempo", httpx.AsyncClient(transport=httpx.MockTransport(slow)))
    assert await waiting.trace(ACME, "f1") == Unavailable(reason="tempo didn't answer in time")


def test_an_id_is_padded_to_whole_hex_and_anything_else_is_left_alone() -> None:
    assert _padded("c029eec9") == "0" * 24 + "c029eec9"
    assert _padded("ABC") == "0" * 29 + "abc"
    assert _padded("f" * 32) == "f" * 32
    assert _padded("f" * 40) == "f" * 40
    assert _padded("zz") == "zz"
    assert _padded("") == ""


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


async def test_a_span_that_reuses_an_id_in_another_form_is_still_another_tenants() -> None:
    # The same 8 bytes, as hex and as base64: one id, two spans, two tenants.
    spans = (
        {**span("x", "acme"), "spanId": "83db6fcbe8c81dba"},
        {**span("x", "globex"), "spanId": "g9tvy+jIHbo="},
    )
    tool = Tool({"/api/v2/traces/f1": json(document(*spans))})
    assert await Tempo("http://tempo", tool.client()).trace(ACME, "f1") == Ok(data=None)


def test_a_span_is_kept_once_the_first() -> None:
    first = Span(
        span_id="1", parent_id=None, name="first", start_ns=1, end_ns=2, attributes={}, error=False
    )
    again = first.model_copy(update={"name": "again"})
    other = first.model_copy(update={"span_id": "2"})
    assert _without_repeats([first, other, again]) == [first, other]
    assert _without_repeats([]) == []


async def test_a_name_is_cut_arrays_are_rendered_and_a_span_asked_in_capitals_is_found() -> None:
    long = span("1", "acme")
    long["name"] = "select " + "x" * 400
    long["attributes"] += [
        {
            "key": "gen_ai.response.finish_reasons",
            "value": {"arrayValue": {"values": [{"stringValue": "stop"}, {"intValue": "2"}]}},
        },
        {
            "key": "gen_ai.tool.call.arguments",
            "value": {"kvlistValue": {"values": [{"key": "a", "value": {"boolValue": True}}]}},
        },
    ]
    tool = Tool({"/api/v2/traces/f1": json(document(long))})
    tempo = Tempo("http://tempo", tool.client())
    plain = await tempo.trace(ACME, "f1")
    assert isinstance(plain, Ok)
    assert plain.data is not None
    (shown,) = plain.data.spans
    assert len(shown.name) == 200
    assert shown.attributes["gen_ai.response.finish_reasons"] == '["stop", 2]'
    assert shown.withheld == ("gen_ai.tool.call.arguments",)
    whole = await tempo.trace(ACME, "f1", reveal="1")
    assert isinstance(whole, Ok)
    assert whole.data is not None
    assert whole.data.spans[0].attributes["gen_ai.tool.call.arguments"] == '{"a": true}'
    # A span's id asked for in capitals is the same span.
    hex_span = {**span("x", "acme"), "spanId": "83DB6FCBE8C81DBA"}
    hex_span["attributes"] += [{"key": "gen_ai.input.messages", "value": {"stringValue": "[x]"}}]
    tool = Tool({"/api/v2/traces/f2": json(document(hex_span))})
    revealed = await Tempo("http://tempo", tool.client()).trace(
        ACME, "f2", reveal="83DB6FCBE8C81DBA"
    )
    assert isinstance(revealed, Ok)
    assert revealed.data is not None
    assert revealed.data.spans[0].withheld == ()
