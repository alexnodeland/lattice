"""The usage read: a tenant's spend per day from its LiteLLM team, and each workspace's tag."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from lattice_core.tags import workspace_tag
from portalr.readers import LiteLLM, Ok, Unavailable, UsageQuery, read_usage
from portalr.readers.litellm import Spend
from portalr.readers.usage import budget_days, daily_budget
from portalr.tenant import allowed
from tests.tools import Tool, json

ACME = allowed("acme")
START = datetime(2026, 10, 11, tzinfo=UTC)
WINDOW = UsageQuery(start=START, end=START + timedelta(days=2), workspaces=["notes", "plans"])
INFO = {
    "team_info": {"team_id": "tenant-acme", "spend": 9, "max_budget": 100, "budget_duration": "30d"}
}


def day(at: str, **entities: tuple[float, int, int]) -> dict[str, Any]:
    """A day of LiteLLM's activity: each entity's spend, tokens and requests."""
    return {
        "date": at,
        "breakdown": {
            "entities": {
                name: {
                    "metrics": {"spend": spend, "total_tokens": tokens, "api_requests": requests}
                }
                for name, (spend, tokens, requests) in entities.items()
            }
        },
    }


async def test_workspace_ids_with_a_percent_a_slash_or_a_comma_round_trip_through_the_read() -> (
    None
):
    odd = ["100%", "a%2Fb", "q3,plan", "eu/west"]
    tags = {
        "results": [
            day(
                "2026-10-11",
                **{
                    workspace_tag("acme", workspace): (float(at + 1), 10, 1)
                    for at, workspace in enumerate(odd)
                },
                # Not asked after: "100%25" is another workspace, which "100%" doesn't name.
                **{workspace_tag("acme", "100%25"): (50.0, 1, 1)},
                # Another tenant's workspace of the same id is never counted.
                **{workspace_tag("globex", "100%"): (60.0, 1, 1)},
            )
        ]
    }
    tool = Tool(
        {
            "/team/info": json(INFO),
            "/team/daily/activity": json({"results": []}),
            "/tag/daily/activity": json(tags),
        }
    )
    query = UsageQuery(start=START, end=START + timedelta(days=1), workspaces=odd)
    read = await read_usage(LiteLLM("http://litellm", tool.client()), ACME, query)
    assert isinstance(read, Ok)
    assert {w.workspace: w.spend for w in read.data.workspaces} == {
        "eu/west": 4.0,
        "q3,plan": 3.0,
        "a%2Fb": 2.0,
        "100%": 1.0,
    }
    asked = next(r.url.params for r in tool.requests if r.url.path == "/tag/daily/activity")
    # The tags asked for are lattice-core's, encoded: no comma but the list's own.
    assert asked["tags"].split(",") == [workspace_tag("acme", workspace) for workspace in odd]


def test_a_workspace_name_is_any_text_but_a_nul() -> None:
    names = ["100%", "a b", "é", "x" * 256]
    assert (
        UsageQuery(start=START, end=START + timedelta(days=1), workspaces=names).workspaces == names
    )
    for bad in ("", "a\x00b", "x" * 257):
        with pytest.raises(ValidationError):
            UsageQuery(start=START, end=START + timedelta(days=1), workspaces=[bad])


def test_a_window_is_at_most_its_most_days_and_names_at_most_fifty_workspaces() -> None:
    with pytest.raises(ValidationError, match="at most 91 days"):
        UsageQuery(start=START, end=START + timedelta(days=92))
    with pytest.raises(ValidationError):
        UsageQuery(
            start=START, end=START + timedelta(days=1), workspaces=[f"w{n}" for n in range(51)]
        )


async def test_spend_per_day_and_per_workspace_from_the_teams_and_the_tenants_tags_alone() -> None:
    team = {
        "results": [
            day("2026-10-11", **{"tenant-acme": (1.5, 100, 3)}),
            # Another team's, though only acme's was asked for: left out.
            day("2026-10-12", **{"tenant-acme": (2.0, 200, 4), "tenant-globex": (50.0, 1, 1)}),
        ],
        "metadata": {"page": 1, "total_pages": 1},
    }
    tags = {
        "results": [
            day("2026-10-11", **{"tenant-workspace:acme/notes": (1.0, 60, 2)}),
            day(
                "2026-10-12",
                **{
                    "tenant-workspace:acme/notes": (0.5, 40, 1),
                    "tenant-workspace:acme/plans": (2.0, 150, 3),
                    # Another tenant's workspace of the same name: never counted as acme's.
                    "tenant-workspace:globex/notes": (99.0, 9, 9),
                },
            ),
        ],
    }
    tool = Tool(
        {
            "/team/info": json(INFO),
            "/team/daily/activity": json(team),
            "/tag/daily/activity": json(tags),
        }
    )
    read = await read_usage(LiteLLM("http://litellm", tool.client()), ACME, WINDOW)
    assert isinstance(read, Ok)
    usage = read.data
    assert [(d.day, d.spend, d.tokens, d.requests) for d in usage.days] == [
        (date(2026, 10, 11), 1.5, 100, 3),
        (date(2026, 10, 12), 2.0, 200, 4),
    ]
    assert [(w.workspace, w.spend, w.tokens) for w in usage.workspaces] == [
        ("plans", 2.0, 150),
        ("notes", 1.5, 100),
    ]
    assert usage.budget is not None
    assert usage.budget.max_budget == 100
    assert usage.daily_budget == pytest.approx(100 / 30)
    assert usage.complete
    asked = {r.url.path: r.url.params for r in tool.requests}
    assert asked["/team/daily/activity"]["team_ids"] == "tenant-acme"
    assert asked["/team/daily/activity"]["start_date"] == "2026-10-11"
    assert asked["/team/daily/activity"]["end_date"] == "2026-10-12"
    assert asked["/tag/daily/activity"]["tags"] == (
        "tenant-workspace:acme/notes,tenant-workspace:acme/plans"
    )


async def test_without_workspaces_no_tag_is_asked_after() -> None:
    tool = Tool({"/team/info": json(INFO), "/team/daily/activity": json({"results": []})})
    query = UsageQuery(start=START, end=START + timedelta(days=1))
    read = await read_usage(LiteLLM("http://litellm", tool.client()), ACME, query)
    assert isinstance(read, Ok)
    assert read.data.workspaces == []
    assert [d.spend for d in read.data.days] == [0]
    assert not any(r.url.path == "/tag/daily/activity" for r in tool.requests)


async def test_every_page_is_read_up_to_the_most(monkeypatch: Any) -> None:
    monkeypatch.setattr("portalr.readers.usage.MOST_PAGES", 2)

    def pages(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            json={
                "results": [day(f"2026-10-1{page}", **{"tenant-acme": (1.0, 1, 1)})],
                "metadata": {"page": page, "total_pages": 3},
            },
        )

    tool = Tool({"/team/info": json(INFO), "/team/daily/activity": pages})
    query = UsageQuery(start=START, end=START + timedelta(days=3))
    read = await read_usage(LiteLLM("http://litellm", tool.client()), ACME, query)
    assert isinstance(read, Ok)
    assert not read.data.complete
    # The third day was never reached, and the second, read last, may be part-read: both are
    # unknown, not 0, so neither is in the answer.
    assert [(d.day.day, d.spend) for d in read.data.days] == [(11, 1.0)]


async def test_a_day_with_no_spend_inside_what_a_partial_read_reached_is_a_measured_zero(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr("portalr.readers.usage.MOST_PAGES", 3)
    # Rows for the 11th, the 13th and the 14th, and no row for the 12th: nothing was spent.
    on = {1: "2026-10-11", 2: "2026-10-13", 3: "2026-10-14"}

    def pages(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            json={
                "results": [day(on[page], **{"tenant-acme": (1.0, 1, 1)})],
                "metadata": {"page": page, "total_pages": 9},
            },
        )

    tool = Tool({"/team/info": json(INFO), "/team/daily/activity": pages})
    query = UsageQuery(start=START, end=START + timedelta(days=5))
    read = await read_usage(LiteLLM("http://litellm", tool.client()), ACME, query)
    assert isinstance(read, Ok)
    assert not read.data.complete
    # The 14th was read last, and the 15th never: left out. The 12th is a 0 between two reads.
    assert [(d.day.day, d.spend) for d in read.data.days] == [(11, 1.0), (12, 0), (13, 1.0)]


async def test_a_partial_read_of_one_day_leaves_it_out_as_it_may_be_part_read(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr("portalr.readers.usage.MOST_PAGES", 1)
    team = {
        "results": [day("2026-10-11", **{"tenant-acme": (1.0, 1, 1)})],
        "metadata": {"page": 1, "total_pages": 2},
    }
    tool = Tool({"/team/info": json(INFO), "/team/daily/activity": json(team)})
    query = UsageQuery(start=START, end=START + timedelta(days=2))
    read = await read_usage(LiteLLM("http://litellm", tool.client()), ACME, query)
    assert isinstance(read, Ok)
    assert not read.data.complete
    assert read.data.days == []


async def test_a_tags_activity_stopped_at_the_page_cap_makes_the_read_partial(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr("portalr.readers.usage.MOST_PAGES", 1)
    team = {"results": [day("2026-10-11", **{"tenant-acme": (1.0, 1, 1)})]}
    tags = {
        "results": [day("2026-10-11", **{"tenant-workspace:acme/notes": (0.5, 5, 1)})],
        "metadata": {"page": 1, "total_pages": 2},
    }
    tool = Tool(
        {
            "/team/info": json(INFO),
            "/team/daily/activity": json(team),
            "/tag/daily/activity": json(tags),
        }
    )
    query = UsageQuery(start=START, end=START + timedelta(days=1), workspaces=["notes"])
    read = await read_usage(LiteLLM("http://litellm", tool.client()), ACME, query)
    assert isinstance(read, Ok)
    # The team's days were read to their end; only the workspaces' split is partial.
    assert not read.data.complete
    assert [d.spend for d in read.data.days] == [1.0]
    assert [(w.workspace, w.spend) for w in read.data.workspaces] == [("notes", 0.5)]


async def test_a_day_split_across_pages_is_summed() -> None:
    def pages(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            json={
                "results": [day("2026-10-11", **{"tenant-acme": (1.0, 10, 1)})],
                "metadata": {"page": page, "total_pages": 2},
            },
        )

    tool = Tool({"/team/info": json(INFO), "/team/daily/activity": pages})
    query = UsageQuery(start=START, end=START + timedelta(days=1))
    read = await read_usage(LiteLLM("http://litellm", tool.client()), ACME, query)
    assert isinstance(read, Ok)
    assert read.data.complete
    assert [(d.spend, d.tokens, d.requests) for d in read.data.days] == [(2.0, 20, 2)]


async def test_a_read_past_its_deadline_before_the_teams_activity_is_unavailable(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr("portalr.readers.usage.DEADLINE", 0.05)

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    litellm = LiteLLM("http://litellm", httpx.AsyncClient(transport=httpx.MockTransport(slow)))
    read = await read_usage(litellm, ACME, WINDOW)
    assert read == Unavailable(reason="litellm didn't answer in time")


async def test_a_read_past_its_deadline_answers_what_it_read(monkeypatch: Any) -> None:
    monkeypatch.setattr("portalr.readers.usage.DEADLINE", 0.2)
    team = {"results": [day("2026-10-11", **{"tenant-acme": (1.5, 100, 3)})]}

    async def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/team/daily/activity":
            return httpx.Response(200, json=team)
        # The budget and the workspaces' tags take too long.
        await asyncio.sleep(5)
        return httpx.Response(200, json={})

    litellm = LiteLLM("http://litellm", httpx.AsyncClient(transport=httpx.MockTransport(answer)))
    read = await read_usage(litellm, ACME, WINDOW)
    assert isinstance(read, Ok)
    # The team's activity was read to its end: a day with nothing in it is a measured 0.
    assert [d.spend for d in read.data.days] == [1.5, 0]
    assert read.data.workspaces == []
    # The budget hadn't answered by the deadline, so it is None, and its share with it.
    assert read.data.budget is None
    assert read.data.daily_budget is None
    assert not read.data.complete
    assert asyncio.all_tasks() == {asyncio.current_task()}


async def test_a_read_refused_stops_the_others() -> None:
    finished: list[str] = []

    async def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/team/info":
            return httpx.Response(503)
        await asyncio.sleep(5)
        finished.append(request.url.path)
        return httpx.Response(200, json={"results": []})

    litellm = LiteLLM("http://litellm", httpx.AsyncClient(transport=httpx.MockTransport(answer)))
    async with asyncio.timeout(1):
        read = await read_usage(litellm, ACME, WINDOW)
    assert read == Unavailable(reason="litellm answered 503")
    assert finished == []
    assert asyncio.all_tasks() == {asyncio.current_task()}


async def test_a_litellm_without_its_activity_is_unavailable() -> None:
    no_team = Tool({"/team/info": json(INFO)})
    assert await read_usage(
        LiteLLM("http://litellm", no_team.client()), ACME, WINDOW
    ) == Unavailable(reason="litellm has no /team/daily/activity at that address")
    no_tags = Tool({"/team/info": json(INFO), "/team/daily/activity": json({"results": []})})
    assert await read_usage(
        LiteLLM("http://litellm", no_tags.client()), ACME, WINDOW
    ) == Unavailable(reason="litellm has no /tag/daily/activity at that address")
    down = Tool({"/team/info": json({}, status=503)})
    read = await read_usage(LiteLLM("http://litellm", down.client()), ACME, WINDOW)
    assert read == Unavailable(reason="litellm answered 503")


@pytest.mark.parametrize(
    ("duration", "days"),
    [
        ("30d", 30),
        ("1mo", 30),
        ("2w", 14),
        ("24h", 1),
        ("1440m", 1),
        ("86400s", 1),
        ("monthly", 30),
        (" Daily ", 1),
        ("0d", None),
        ("30", None),
        ("thirty days", None),
        ("30d extra", None),
    ],
)
def test_a_budget_duration_is_read_as_litellm_reads_it(duration: str, days: float | None) -> None:
    assert budget_days(duration) == (pytest.approx(days) if days is not None else None)


def test_a_days_share_of_the_budget_needs_a_budget_and_a_duration() -> None:
    assert daily_budget(Spend(spend=1, max_budget=70, budget_duration="7d")) == 10
    assert daily_budget(None) is None
    assert daily_budget(Spend(spend=1)) is None
    assert daily_budget(Spend(spend=1, max_budget=0, budget_duration="7d")) is None
    assert daily_budget(Spend(spend=1, max_budget=70)) is None
    assert daily_budget(Spend(spend=1, max_budget=70, budget_duration="soon")) is None


def test_a_workspace_asked_after_twice_is_asked_after_once() -> None:
    query = UsageQuery(start=START, end=START + timedelta(days=1), workspaces=["b", "a", "b"])
    assert query.workspaces == ["b", "a"]
