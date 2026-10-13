"""The feedback summary: every score in a window, read to the end, and summed by day."""

import importlib
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from portalr.readers import FeedbackQuery, Langfuse, Ok, Score, Unavailable, Window, feedback
from portalr.readers.feedback import COMMENTS, days_in, summarize
from portalr.readers.langfuse import MOST_SCORES
from portalr.tenant import allowed
from tests.tools import Tool, json

ACME = allowed("acme")
START = datetime(2026, 10, 11, tzinfo=UTC)
WINDOW = FeedbackQuery(start=START, end=START + timedelta(days=2))


def score(at: str, value: float | bool | str, evaluator: str | None = None, **fields: Any) -> Score:
    data_type = "BOOLEAN" if isinstance(value, bool) else fields.pop("data_type", "NUMERIC")
    return Score(
        id=f"{at}-{value}-{evaluator}",
        trace_id="t1",
        name=fields.pop("name", "thumbs"),
        data_type=data_type,
        value=value,
        source="API",
        timestamp=datetime.fromisoformat(at),
        evaluator=evaluator,
        **fields,
    )


def test_a_window_is_each_day_it_touches() -> None:
    assert days_in(WINDOW) == [date(2026, 10, 11), date(2026, 10, 12)]
    late = Window(start=START, end=START + timedelta(days=1, hours=1))
    assert days_in(late) == [date(2026, 10, 11), date(2026, 10, 12)]


def test_thumbs_and_evaluations_are_summed_by_day() -> None:
    summary = summarize(
        [
            score("2026-10-11T09:00:00+00:00", True, workspace="notes"),
            score("2026-10-11T10:00:00+00:00", False, workspace="notes", comment="wrong"),
            score("2026-10-12T10:00:00+00:00", True, comment="great"),
            score("2026-10-11T09:00:00+00:00", 0.5, "accuracy", name="accuracy"),
            score("2026-10-11T11:00:00+00:00", 1, "accuracy", name="accuracy"),
            score("2026-10-12T11:00:00+00:00", False, "safety", name="safe", workspace="plans"),
            score(
                "2026-10-12T11:00:00+00:00", "good", "tone", name="tone", data_type="CATEGORICAL"
            ),
            # Outside the window's days: in the totals by workspace, not in a day.
            score("2026-10-01T11:00:00+00:00", True, workspace="notes"),
            # A person's number: neither a thumb nor an evaluation.
            score("2026-10-11T11:00:00+00:00", 3),
        ],
        WINDOW,
    )
    assert [(t.day.day, t.up, t.down) for t in summary.days] == [(11, 1, 1), (12, 1, 0)]
    assert [(e.evaluator, e.name, e.count) for e in summary.evaluations] == [
        ("accuracy", "accuracy", 2),
        ("safety", "safe", 1),
    ]
    accuracy = summary.evaluations[0]
    assert [(m.day.day, m.count, m.mean) for m in accuracy.days] == [(11, 2, 0.75), (12, 0, None)]
    assert summary.evaluations[1].days[1].mean == 0.0
    assert [(p.workspace, p.up, p.down, p.evaluated) for p in summary.workspaces] == [
        (None, 1, 0, 3),
        ("notes", 2, 1, 0),
        ("plans", 0, 0, 1),
    ]
    assert [c.comment for c in summary.comments] == ["great", "wrong"]
    assert summary.complete


def test_the_newest_comments_alone_are_carried_and_a_full_read_is_partial() -> None:
    said = [
        score(f"2026-10-11T{n // 60:02}:{n % 60:02}:00+00:00", True, comment=f"c{n}")
        for n in range(COMMENTS + 5)
    ]
    summary = summarize(said, WINDOW)
    assert len(summary.comments) == COMMENTS
    assert summary.comments[0].comment == f"c{COMMENTS + 4}"
    many = [said[0]] * MOST_SCORES
    assert not summarize(many, WINDOW).complete


def paged(pages: list[dict[str, Any]]):
    """Answer each request with the page its cursor names: the first without one."""

    def answer(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        return httpx.Response(200, json=pages[int(cursor) if cursor else 0])

    return answer


async def test_every_score_is_read_to_the_end_of_every_page() -> None:
    observations = [
        {
            "data": [{"traceId": "t1", "tags": ["tenant:acme", "workspace:notes"]}],
            "meta": {"cursor": "1"},
        },
        {"data": [{"traceId": "t2", "tags": ["tenant:acme"]}], "meta": {}},
    ]
    thumb = {"name": "thumbs", "dataType": "BOOLEAN", "source": "API"}
    scores = [
        {
            "data": [
                {
                    **thumb,
                    "id": "s1",
                    "value": True,
                    "timestamp": "2026-10-11T01:00:00Z",
                    "subject": {"kind": "trace", "id": "t1"},
                },
            ],
            "meta": {"cursor": "1"},
        },
        {
            "data": [
                {
                    **thumb,
                    "id": "s2",
                    "value": False,
                    "timestamp": "2026-10-12T01:00:00Z",
                    "subject": {"kind": "trace", "id": "t2"},
                },
            ],
        },
    ]
    tool = Tool(
        {"/api/public/v2/observations": paged(observations), "/api/public/v3/scores": paged(scores)}
    )
    langfuse = Langfuse("http://langfuse", project="p1", client=tool.client())
    read = await feedback(langfuse, ACME, WINDOW.model_copy(update={"workspace": "notes"}))
    assert isinstance(read, Ok)
    assert [(t.up, t.down) for t in read.data.days] == [(1, 0), (0, 1)]
    assert [p.workspace for p in read.data.workspaces] == [None, "notes"]
    asked = [request.url for request in tool.requests]
    assert [url.params.get("cursor") for url in asked] == [None, "1", None, "1"]
    assert '"workspace:notes"' in asked[0].params["filter"]
    assert asked[0].params["limit"] == "1000"
    assert asked[2].params["limit"] == "100"


async def test_a_langfuse_without_its_apis_is_unavailable_to_the_summary() -> None:
    tool = Tool({"/api/public/v2/observations": json({"data": [], "meta": {}})})
    langfuse = Langfuse("http://langfuse", project="p1", client=tool.client())
    read = await feedback(langfuse, ACME, WINDOW)
    assert isinstance(read, Ok)
    assert read.data.evaluations == []
    down = Langfuse("http://langfuse", project="p1", client=Tool().client())
    assert await feedback(down, ACME, WINDOW) == Unavailable(
        reason="langfuse has no observations API at that address"
    )


async def test_a_read_past_the_most_scores_stops_and_says_it_is_partial(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr("portalr.readers.langfuse.MOST_SCORES", 1)
    monkeypatch.setattr(importlib.import_module("portalr.readers.feedback"), "MOST_SCORES", 1)
    traces = [{"traceId": f"t{n:03}", "tags": ["tenant:acme"]} for n in range(60)]
    one = {
        "data": [
            {
                "id": "s1",
                "name": "thumbs",
                "dataType": "BOOLEAN",
                "source": "API",
                "value": True,
                "timestamp": "2026-10-11T01:00:00Z",
                "subject": {"kind": "trace", "id": "t000"},
            },
        ],
        "meta": {"cursor": "more"},
    }
    tool = Tool(
        {"/api/public/v2/observations": json({"data": traces}), "/api/public/v3/scores": json(one)}
    )
    langfuse = Langfuse("http://langfuse", project="p1", client=tool.client())
    read = await feedback(langfuse, ACME, WINDOW)
    assert isinstance(read, Ok)
    assert not read.data.complete
    assert sum(1 for request in tool.requests if request.url.path.endswith("/scores")) == 1


async def test_a_langfuse_without_its_score_api_is_unavailable() -> None:
    tool = Tool(
        {
            "/api/public/v2/observations": json(
                {"data": [{"traceId": "t1", "tags": ["tenant:acme"]}]}
            )
        }
    )
    langfuse = Langfuse("http://langfuse", project="p1", client=tool.client())
    assert await feedback(langfuse, ACME, WINDOW) == Unavailable(
        reason="langfuse has no scores API at that address"
    )
