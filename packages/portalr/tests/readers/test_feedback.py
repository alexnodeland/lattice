"""The feedback summary: the scores in a window, read within bounds, and summed by day in UTC."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from portalr.readers import FeedbackQuery, Langfuse, Ok, Score, Unavailable, read_feedback
from portalr.readers.feedback import COMMENTS, days_in, summarize
from portalr.readers.langfuse import Scores, trace_parameters
from portalr.readers.query import Span
from portalr.tenant import allowed
from tests.tools import Tool, json

ACME = allowed("acme")
START = datetime(2026, 10, 11, tzinfo=UTC)
WINDOW = FeedbackQuery(start=START, end=START + timedelta(days=2))
AT = "2026-10-11T00:00:00Z"


def score(at: str, value: float | bool | str, evaluator: str | None = None, **fields: Any) -> Score:
    data_type = fields.pop("data_type", "BOOLEAN" if isinstance(value, bool) else "NUMERIC")
    return Score(
        id=f"{at}-{value}-{evaluator}-{fields.get('name', '')}",
        trace_id="t1",
        name=fields.pop("name", "thumbs.up"),
        data_type=data_type,
        value=value,
        source=fields.pop("source", "API"),
        timestamp=datetime.fromisoformat(at),
        evaluator=evaluator,
        feedback_type=fields.pop("feedback_type", None if evaluator else "thumbs"),
        **fields,
    )


def test_a_window_is_each_day_it_touches_in_utc() -> None:
    assert days_in(WINDOW) == [date(2026, 10, 11), date(2026, 10, 12)]
    late = Span(start=START, end=START + timedelta(days=1, hours=1))
    assert days_in(late) == [date(2026, 10, 11), date(2026, 10, 12)]
    elsewhere = Span(
        start=datetime.fromisoformat("2026-10-11T02:00:00+02:00"),
        end=datetime.fromisoformat("2026-10-12T02:00:00+02:00"),
    )
    assert days_in(elsewhere) == [date(2026, 10, 11)]


def test_a_window_ends_after_it_starts_and_is_at_most_a_quarter() -> None:
    with pytest.raises(ValidationError, match="ends after it starts"):
        FeedbackQuery(start=START, end=START)
    assert FeedbackQuery(start=START, end=START + timedelta(days=91)).end
    with pytest.raises(ValidationError, match="at most 91 days"):
        FeedbackQuery(start=START, end=START + timedelta(days=91, seconds=1))


def test_thumbs_evaluations_and_comments_are_summed_by_day() -> None:
    summary = summarize(
        Scores(
            scores=[
                score("2026-10-11T09:00:00+00:00", True, workspace="notes"),
                # Langfuse sends a yes-or-no as 1 or 0: read as a number, a thumb all the same.
                score("2026-10-11T10:00:00+00:00", 0.0, workspace="notes", data_type="BOOLEAN"),
                score("2026-10-12T10:00:00+00:00", 1.0, data_type="BOOLEAN"),
                score(
                    "2026-10-12T10:01:00+00:00", "great", name="thumbs.comment", data_type="TEXT"
                ),
                score("2026-10-11T10:02:00+00:00", 0.0, comment="wrong", data_type="BOOLEAN"),
                score("2026-10-11T09:00:00+00:00", 0.5, "accuracy", name="accuracy"),
                score("2026-10-11T11:00:00+00:00", 1, "accuracy", name="accuracy"),
                score(
                    "2026-10-12T11:00:00+00:00",
                    0.0,
                    "safety",
                    name="safe",
                    data_type="BOOLEAN",
                    workspace="plans",
                ),
                score(
                    "2026-10-12T11:00:00+00:00",
                    "good",
                    "tone",
                    name="tone",
                    data_type="CATEGORICAL",
                ),
                # A score given in another zone is counted on its day in UTC.
                score("2026-10-12T01:00:00+02:00", True),
                # Not a person's: an annotation in Langfuse's own UI.
                score("2026-10-11T11:00:00+00:00", True, source="ANNOTATION"),
                # A person's number: neither a thumb nor what they wrote.
                score("2026-10-11T11:00:00+00:00", 3),
                # A person's yes-or-no of another feedback type: not a thumb.
                score("2026-10-11T11:00:00+00:00", True, feedback_type="helpful"),
            ],
            complete=True,
        ),
        WINDOW,
    )
    assert [(t.day.day, t.up, t.down) for t in summary.days] == [(11, 2, 2), (12, 1, 0)]
    assert [(e.evaluator, e.name, e.count) for e in summary.evaluations] == [
        ("accuracy", "accuracy", 2),
        ("safety", "safe", 1),
    ]
    accuracy = summary.evaluations[0]
    assert [(m.day.day, m.count, m.mean) for m in accuracy.days] == [(11, 2, 0.75), (12, 0, None)]
    assert summary.evaluations[1].days[1].mean == 0.0
    assert [(p.workspace, p.up, p.down, p.evaluated) for p in summary.workspaces] == [
        # A categorical verdict isn't averaged, but is counted among the workspace's evaluations.
        (None, 2, 1, 3),
        ("notes", 1, 1, 0),
        ("plans", 0, 0, 1),
    ]
    assert [c.text for c in summary.comments] == ["great", "wrong"]
    assert summary.complete
    assert summary.known_from is None


def test_the_days_before_the_oldest_trace_read_are_unknown() -> None:
    def stopped(at: str) -> Scores:
        return Scores(scores=[], complete=False, known_from=datetime.fromisoformat(at))

    # The oldest trace read started on the 11th: the 12th on is known, the 11th isn't.
    assert summarize(stopped("2026-10-11T10:00:00+00:00"), WINDOW).known_from == date(2026, 10, 12)
    # It started before the window: every day of it is known.
    assert summarize(stopped("2026-10-10T10:00:00+00:00"), WINDOW).known_from is None


def test_the_newest_comments_alone_are_carried_and_a_partial_read_says_so() -> None:
    said = [
        score(f"2026-10-11T{n // 60:02}:{n % 60:02}:00+00:00", True, comment=f"c{n}")
        for n in range(COMMENTS + 5)
    ]
    summary = summarize(Scores(scores=said, complete=False), WINDOW)
    assert len(summary.comments) == COMMENTS
    assert summary.comments[0].text == f"c{COMMENTS + 4}"
    assert not summary.complete


def paged(pages: list[dict[str, Any]]):
    """Answer each request with the page its cursor names: the first without one."""

    def answer(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        return httpx.Response(200, json=pages[int(cursor) if cursor else 0])

    return answer


def thumb(id: str, trace: str, value: int, at: str = "2026-10-11T01:00:00Z") -> dict[str, Any]:
    """A thumb as Langfuse 4's v3 score API sends it: a yes-or-no, as 1 or 0."""
    return {
        "id": id,
        "name": "thumbs.up",
        "dataType": "BOOLEAN",
        "source": "API",
        "value": value,
        "timestamp": at,
        "subject": {"kind": "trace", "id": trace},
        "metadata": {"feedback_type": "thumbs"},
    }


async def test_every_page_is_read_and_a_named_workspaces_tag_is_checked_again() -> None:
    observations = [
        {
            "data": [
                {"traceId": "t1", "startTime": AT, "tags": ["tenant:acme", "workspace:notes"]}
            ],
            "meta": {"cursor": "1"},
        },
        # Langfuse ignored the workspace's tag: a trace in another workspace is left out.
        {"data": [{"traceId": "t2", "startTime": AT, "tags": ["tenant:acme", "workspace:plans"]}]},
    ]
    scores = [
        {"data": [thumb("s1", "t1", 1)], "meta": {"cursor": "1"}},
        {"data": [thumb("s2", "t1", 0, "2026-10-12T01:00:00Z")], "meta": {}},
    ]
    tool = Tool(
        {"/api/public/v2/observations": paged(observations), "/api/public/v3/scores": paged(scores)}
    )
    langfuse = Langfuse("http://langfuse", project="p1", client=tool.client())
    read = await read_feedback(langfuse, ACME, WINDOW.model_copy(update={"workspace": "notes"}))
    assert isinstance(read, Ok)
    assert [(t.up, t.down) for t in read.data.days] == [(1, 0), (0, 1)]
    assert [p.workspace for p in read.data.workspaces] == ["notes"]
    assert read.data.complete
    asked = [request.url for request in tool.requests]
    assert [url.params.get("cursor") for url in asked] == [None, "1", None, "1"]
    assert '"workspace:notes"' in asked[0].params["filter"]
    # Traces from a week before the window, so a late thumb on one is counted.
    assert '"2026-10-04T00:00:00+00:00"' in asked[0].params["filter"]
    assert asked[0].params["limit"] == "1000"
    assert asked[2].params["traceId"] == "t1"
    assert asked[2].params["fromTimestamp"] == "2026-10-11T00:00:00+00:00"
    assert asked[2].params["limit"] == "100"


async def test_a_trace_cursor_that_comes_round_again_ends_the_read_partial() -> None:
    looping = {
        "data": [{"traceId": "t1", "startTime": AT, "tags": ["tenant:acme"]}],
        "meta": {"cursor": "0"},
    }
    tool = Tool(
        {
            "/api/public/v2/observations": paged([looping]),
            "/api/public/v3/scores": json({"data": [thumb("s1", "t1", 1)]}),
        }
    )
    langfuse = Langfuse("http://langfuse", project="p1", client=tool.client())
    read = await langfuse.every_score(ACME, WINDOW)
    assert isinstance(read, Ok)
    assert not read.data.complete
    assert read.data.known_from == datetime.fromisoformat(AT)
    assert [s.id for s in read.data.scores] == ["s1"]
    assert len(tool.requests) == 3


async def test_a_score_cursor_that_comes_round_again_ends_the_read_partial_counting_once() -> None:
    tool = Tool(
        {
            "/api/public/v2/observations": json(
                {"data": [{"traceId": "t1", "startTime": AT, "tags": ["tenant:acme"]}]}
            ),
            "/api/public/v3/scores": paged(
                [{"data": [thumb("s1", "t1", 1)], "meta": {"cursor": "0"}}]
            ),
        }
    )
    langfuse = Langfuse("http://langfuse", project="p1", client=tool.client())
    read = await langfuse.every_score(ACME, WINDOW)
    assert isinstance(read, Ok)
    assert not read.data.complete
    # The traces were all read: only the scores stopped short.
    assert read.data.known_from is None
    assert [s.id for s in read.data.scores] == ["s1"]
    assert len(tool.requests) == 3


async def test_traces_past_the_most_pages_make_the_read_partial(monkeypatch: Any) -> None:
    monkeypatch.setattr("portalr.readers.langfuse.MOST_TRACE_PAGES", 2)
    pages = [
        {
            "data": [{"traceId": f"t{n}", "startTime": AT, "tags": ["tenant:acme"]}],
            "meta": {"cursor": str(n + 1)},
        }
        for n in range(5)
    ]
    tool = Tool(
        {"/api/public/v2/observations": paged(pages), "/api/public/v3/scores": json({"data": []})}
    )
    langfuse = Langfuse("http://langfuse", project="p1", client=tool.client())
    read = await langfuse.every_score(ACME, WINDOW)
    assert isinstance(read, Ok)
    assert not read.data.complete
    assert read.data.known_from == datetime.fromisoformat(AT)
    assert sum(r.url.path.endswith("observations") for r in tool.requests) == 2


async def test_traces_not_sent_newest_first_leave_no_day_known(monkeypatch: Any) -> None:
    monkeypatch.setattr("portalr.readers.langfuse.MOST_TRACE_PAGES", 2)
    pages = [
        {
            "data": [{"traceId": f"t{n}", "startTime": at, "tags": ["tenant:acme"]}],
            "meta": {"cursor": str(n + 1)},
        }
        # The second page is newer than the first: Langfuse didn't keep to newest first.
        for n, at in enumerate(["2026-10-11T01:00:00Z", "2026-10-11T02:00:00Z", AT])
    ]
    tool = Tool(
        {"/api/public/v2/observations": paged(pages), "/api/public/v3/scores": json({"data": []})}
    )
    langfuse = Langfuse("http://langfuse", project="p1", client=tool.client())
    read = await langfuse.every_score(ACME, WINDOW)
    assert isinstance(read, Ok)
    assert read.data.known_from == WINDOW.end
    summary = await read_feedback(langfuse, ACME, WINDOW)
    assert isinstance(summary, Ok)
    assert summary.data.known_from == date(2026, 10, 14)


async def test_a_read_stops_at_most_and_exactly_at_it_is_partial() -> None:
    traces = [
        {
            "traceId": f"t{n:03}",
            "startTime": f"2026-10-11T{n % 24:02}:00:00Z",
            "tags": ["tenant:acme"],
        }
        for n in range(60)
    ]

    def scored(request: httpx.Request) -> httpx.Response:
        first = request.url.params["traceId"].split(",")[0]
        if "cursor" in request.url.params:
            return httpx.Response(200, json={"data": []})
        # One score a batch, and a page more, which a read at its most doesn't ask for.
        return httpx.Response(
            200, json={"data": [thumb(f"s-{first}", first, 1)], "meta": {"cursor": "more"}}
        )

    tool = Tool(
        {"/api/public/v2/observations": json({"data": traces}), "/api/public/v3/scores": scored}
    )
    langfuse = Langfuse("http://langfuse", project="p1", client=tool.client())
    one = await langfuse.every_score(ACME, WINDOW, most=1)
    assert isinstance(one, Ok)
    assert len(one.data.scores) == 1
    assert not one.data.complete
    both = await langfuse.every_score(ACME, WINDOW, most=3)
    assert isinstance(both, Ok)
    assert len(both.data.scores) == 2, "two batches of traces, one score each"
    assert both.data.complete


async def test_a_read_past_its_deadline_before_any_trace_is_unavailable(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr("portalr.readers.langfuse.DEADLINE", 0.05)

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={"data": []})

    langfuse = Langfuse(
        "http://langfuse",
        project="p1",
        client=httpx.AsyncClient(transport=httpx.MockTransport(slow)),
    )
    read = await langfuse.every_score(ACME, WINDOW)
    assert read == Unavailable(reason="langfuse didn't answer in time")


async def test_a_read_past_its_deadline_answers_the_scores_it_has(monkeypatch: Any) -> None:
    monkeypatch.setattr("portalr.readers.langfuse.DEADLINE", 0.2)
    monkeypatch.setattr("portalr.readers.langfuse.TRACES_PER_READ", 1)
    traces = [{"traceId": f"t{n}", "startTime": AT, "tags": ["tenant:acme"]} for n in range(2)]

    async def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("observations"):
            return httpx.Response(200, json={"data": traces})
        trace = request.url.params["traceId"]
        if trace == "t1":
            # One batch's scores take too long; the other's are read.
            await asyncio.sleep(5)
        return httpx.Response(200, json={"data": [thumb(f"s-{trace}", trace, 1)]})

    langfuse = Langfuse(
        "http://langfuse",
        project="p1",
        client=httpx.AsyncClient(transport=httpx.MockTransport(answer)),
    )
    read = await langfuse.every_score(ACME, WINDOW)
    assert isinstance(read, Ok)
    assert [s.id for s in read.data.scores] == ["s-t0"]
    assert not read.data.complete
    assert read.data.known_from is None
    # Nothing of the read is left running.
    assert asyncio.all_tasks() == {asyncio.current_task()}


async def test_a_batch_refused_stops_the_others(monkeypatch: Any) -> None:
    monkeypatch.setattr("portalr.readers.langfuse.TRACES_PER_READ", 1)
    traces = [{"traceId": f"t{n}", "startTime": AT, "tags": ["tenant:acme"]} for n in range(2)]
    finished: list[str] = []

    async def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("observations"):
            return httpx.Response(200, json={"data": traces})
        trace = request.url.params["traceId"]
        if trace == "t0":
            return httpx.Response(503)
        await asyncio.sleep(5)
        finished.append(trace)
        return httpx.Response(200, json={"data": []})

    langfuse = Langfuse(
        "http://langfuse",
        project="p1",
        client=httpx.AsyncClient(transport=httpx.MockTransport(answer)),
    )
    async with asyncio.timeout(1):
        read = await langfuse.every_score(ACME, WINDOW)
    assert read == Unavailable(reason="langfuse answered 503")
    assert finished == []
    assert asyncio.all_tasks() == {asyncio.current_task()}


async def test_a_langfuse_without_its_score_api_is_unavailable() -> None:
    tool = Tool(
        {
            "/api/public/v2/observations": json(
                {"data": [{"traceId": "t1", "startTime": AT, "tags": ["tenant:acme"]}]}
            )
        }
    )
    langfuse = Langfuse("http://langfuse", project="p1", client=tool.client())
    assert await read_feedback(langfuse, ACME, WINDOW) == Unavailable(
        reason="langfuse has no scores API at that address"
    )
    down = Langfuse("http://langfuse", project="p1", client=Tool().client())
    assert await read_feedback(down, ACME, WINDOW) == Unavailable(
        reason="langfuse has no observations API at that address"
    )


def test_a_moment_has_its_zone_and_a_span_starts_this_century() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        FeedbackQuery.model_validate(
            {"start": "2026-10-11T00:00:00", "end": "2026-10-12T00:00:00Z"}
        )
    with pytest.raises(ValidationError, match="starts in 2000 or later"):
        Span(start=datetime(1999, 12, 31, tzinfo=UTC), end=START)
    earliest = Span(start=datetime(2000, 1, 1, tzinfo=UTC), end=START)
    assert trace_parameters(ACME, earliest)["filter"].count("1999-12-25T00:00:00+00:00") == 1
