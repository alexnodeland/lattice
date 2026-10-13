"""A tenant's usage and spend by day, from LiteLLM, and each of its workspaces' (portalr ADR-0028).

The tenant's spend per day is its LiteLLM team's, from ``/team/daily/activity``. A workspace's is
its tag's, from ``/tag/daily/activity``: the libraries' gateways tag each request
``tenant-workspace:<tenant>/<workspace>``, so the read asks only for the tags of the tenant's own
workspaces, never for every tag, and keeps only an answer whose tag is one it asked for. Spend
recorded before the tag was sent has no workspace.

A read is bounded, as Feedback's is: so many pages, so long in all; past any bound, it answers what
it read, and says it is partial.
"""

import asyncio
import contextlib
import re
from collections import defaultdict
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from portalr.readers.http import read
from portalr.readers.litellm import LiteLLM, Spend, team
from portalr.readers.query import Id, Span, day_of, days_in
from portalr.readers.reading import Ok, Unavailable
from portalr.tenant import Tenant

MOST_DAYS: Final = 91
"""The longest window a read sums, in days, as Feedback's."""

MOST_WORKSPACES: Final = 50
"""The most workspaces one read asks after."""

MOST_PAGES: Final = 20
"""The most pages of either activity a read takes: past it, the read is partial."""

PAGE_SIZE: Final = 1000
"""How many records a page of LiteLLM's daily activity holds."""

DEADLINE: Final = 20.0
"""How long a read may take, in seconds: past it, the read answers what it has, partial."""

WORKSPACE_TAG: Final = "tenant-workspace:"
"""How a request's tag names its tenant and workspace: ``tenant-workspace:<tenant>/<workspace>``."""


_DURATION: Final = re.compile(r"(\d+)(mo|[smhdw])")
_UNITS: Final = {"s": 1 / 86_400, "m": 1 / 1_440, "h": 1 / 24, "d": 1, "w": 7, "mo": 30}
_ALIASES: Final = {"hourly": "1h", "daily": "24h", "weekly": "7d", "monthly": "30d"}


def budget_days(duration: str) -> float | None:
    """How many days a LiteLLM budget duration is, such as ``30d`` or ``1mo``; None if unread.

    As LiteLLM reads them: seconds, minutes, hours, days, weeks or months, or ``hourly``,
    ``daily``, ``weekly`` or ``monthly``; a month as 30 days.
    """
    named = _ALIASES.get(duration.strip().lower(), duration.strip())
    match = _DURATION.fullmatch(named)
    if match is None or int(match[1]) == 0:
        return None
    return int(match[1]) * _UNITS[match[2]]


def daily_budget(spend: Spend | None) -> float | None:
    """A day's share of the team's budget: the budget over its duration's days; None for none."""
    if spend is None or not spend.max_budget or spend.max_budget <= 0 or not spend.budget_duration:
        return None
    days = budget_days(spend.budget_duration)
    return spend.max_budget / days if days else None


def workspace_tag(tenant: Tenant, workspace: str) -> str:
    """The tag the libraries' gateways send for a workspace's requests."""
    return f"{WORKSPACE_TAG}{tenant.id}/{workspace}"


class UsageQuery(Span):
    """Which usage to read: a window of at most ``MOST_DAYS``, and the workspaces to split it by."""

    workspaces: list[Id] = Field(default_factory=list, max_length=MOST_WORKSPACES)

    @model_validator(mode="after")
    def _at_most_a_quarter(self) -> Self:
        if self.end - self.start > timedelta(days=MOST_DAYS):
            raise ValueError(f"a window is at most {MOST_DAYS} days")
        return self


class DaySpend(BaseModel):
    """What was spent on one day, in UTC: dollars, tokens and requests."""

    model_config = ConfigDict(frozen=True)

    day: date
    spend: float
    tokens: int
    requests: int


class WorkspaceSpend(BaseModel):
    """One workspace's spend over the window, and per day."""

    model_config = ConfigDict(frozen=True)

    workspace: str
    spend: float
    tokens: int
    days: list[DaySpend]


class Usage(BaseModel):
    """The window's spend per day, each workspace's, the team's budget, and whether all was read."""

    model_config = ConfigDict(frozen=True)

    days: list[DaySpend]
    workspaces: list[WorkspaceSpend]
    """The most spent first; a workspace with nothing recorded under its tag isn't in it."""
    budget: Spend | None
    """The team's spend and budget, as ``/team/info`` says; None for a tenant with no team."""
    daily_budget: float | None
    """A day's share of the team's budget; None where it has no budget, or none LiteLLM resets."""
    complete: bool
    """False where a read stopped at one of its bounds."""


class _Metrics(BaseModel):
    spend: float = 0
    total_tokens: int = 0
    api_requests: int = 0

    def __add__(self, other: "_Metrics") -> "_Metrics":
        return _Metrics(
            spend=self.spend + other.spend,
            total_tokens=self.total_tokens + other.total_tokens,
            api_requests=self.api_requests + other.api_requests,
        )


class _Entity(BaseModel):
    metrics: _Metrics = _Metrics()


class _Breakdown(BaseModel):
    entities: dict[str, _Entity] = {}


class _Day(BaseModel):
    date: date
    breakdown: _Breakdown = _Breakdown()


class _Page(BaseModel):
    page: int = 1
    total_pages: int = 1


class _Activity(BaseModel):
    results: list[_Day]
    metadata: _Page = _Page()


_ACTIVITY: Final = TypeAdapter(_Activity)


@dataclass
class _Found:
    """What an activity's pages held, as they are read: each kept entity's metrics per day."""

    by_entity: dict[str, dict[date, _Metrics]] = field(
        default_factory=lambda: defaultdict(dict[date, _Metrics])
    )
    pages: int = 0
    complete: bool = False


class _Stop(Exception):
    """A read was refused: raised in its task so the task group cancels the others."""


async def _activity(
    litellm: LiteLLM, path: str, params: dict[str, str], keep: set[str], found: _Found
) -> Unavailable | None:
    """Each kept entity's metrics per day, from every page, so many at most, added to `found`."""
    for page in range(1, MOST_PAGES + 1):
        answer = await read(
            litellm.client,
            "litellm",
            f"{litellm.url}{path}",
            _ACTIVITY,
            params={**params, "page": str(page), "page_size": str(PAGE_SIZE)},
        )
        if answer is None or isinstance(answer, Unavailable):
            return answer or Unavailable(reason=f"litellm has no {path} at that address")
        for day in answer.results:
            # Only what was asked for: another team's, or another tenant's tag, is left out.
            for entity, metrics in day.breakdown.entities.items():
                if entity in keep:
                    # LiteLLM pages its rows, then groups them by day: a day may be on two pages.
                    by_day = found.by_entity[entity]
                    by_day[day.date] = by_day.get(day.date, _Metrics()) + metrics.metrics
        found.pages = page
        if page >= answer.metadata.total_pages:
            found.complete = True
            return None
    return None


def _days(by_day: dict[date, _Metrics], days: list[date]) -> list[DaySpend]:
    return [
        DaySpend(
            day=day,
            spend=(metrics := by_day.get(day, _Metrics())).spend,
            tokens=metrics.total_tokens,
            requests=metrics.api_requests,
        )
        for day in days
    ]


async def read_usage(
    litellm: LiteLLM, tenant: Tenant, query: UsageQuery
) -> Ok[Usage] | Unavailable:
    """The tenant's spend per day in the window, each of the named workspaces', and its budget.

    The team's activity, the tags' and the budget are read at once; one refused stops the others.
    Past the deadline, it answers what it has read, partial, or, if not a page of the team's
    activity, that LiteLLM didn't answer in time.
    """
    dates = {
        "start_date": day_of(query.start).isoformat(),
        "end_date": day_of(query.end - timedelta(microseconds=1)).isoformat(),
    }
    tags = {workspace_tag(tenant, workspace): workspace for workspace in query.workspaces}
    teams, tagged = _Found(), _Found(complete=not tags)
    spent: list[Spend | None] = []
    refused: list[Unavailable] = []

    async def refusing(reading: Awaitable[Unavailable | None]) -> None:
        if (refusal := await reading) is not None:
            refused.append(refusal)
            raise _Stop

    async def budget() -> Unavailable | None:
        answer = await litellm.spend(tenant)
        if isinstance(answer, Unavailable):
            return answer
        spent.append(answer.data)
        return None

    try:
        async with asyncio.timeout(DEADLINE):
            with contextlib.suppress(_Stop):
                async with asyncio.TaskGroup() as group:
                    group.create_task(refusing(budget()))
                    group.create_task(
                        refusing(
                            _activity(
                                litellm,
                                "/team/daily/activity",
                                {"team_ids": team(tenant), **dates},
                                {team(tenant)},
                                teams,
                            )
                        )
                    )
                    if tags:
                        group.create_task(
                            refusing(
                                _activity(
                                    litellm,
                                    "/tag/daily/activity",
                                    {"tags": ",".join(tags), **dates},
                                    set(tags),
                                    tagged,
                                )
                            )
                        )
    except TimeoutError:
        if teams.pages == 0:
            return Unavailable(reason="litellm didn't answer in time")
    if refused:
        return refused[0]
    days = days_in(query)
    workspaces = [
        WorkspaceSpend(
            workspace=tags[tag],
            spend=sum(metrics.spend for metrics in by_day.values()),
            tokens=sum(metrics.total_tokens for metrics in by_day.values()),
            days=_days(by_day, days),
        )
        for tag, by_day in tagged.by_entity.items()
    ]
    budgeted = spent[0] if spent else None
    return Ok(
        data=Usage(
            days=_days(teams.by_entity.get(team(tenant), {}), days),
            workspaces=sorted(workspaces, key=lambda w: (-w.spend, w.workspace)),
            budget=budgeted,
            daily_budget=daily_budget(budgeted),
            complete=teams.complete and tagged.complete and bool(spent),
        )
    )
