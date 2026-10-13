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
from collections import defaultdict
from datetime import date, timedelta
from typing import Annotated, Final, Self

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


def workspace_tag(tenant: Tenant, workspace: str) -> str:
    """The tag the libraries' gateways send for a workspace's requests."""
    return f"{WORKSPACE_TAG}{tenant.id}/{workspace}"


class UsageQuery(Span):
    """Which usage to read: a window of at most ``MOST_DAYS``, and the workspaces to split it by."""

    workspaces: Annotated[list[Id], Field(default_factory=list, max_length=MOST_WORKSPACES)]

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
    complete: bool
    """False where a read stopped at one of its bounds."""


class _Metrics(BaseModel):
    spend: float = 0
    total_tokens: int = 0
    api_requests: int = 0


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


async def _activity(
    litellm: LiteLLM, path: str, params: dict[str, str], keep: set[str]
) -> tuple[dict[str, dict[date, _Metrics]], bool] | Unavailable:
    """Each kept entity's metrics per day, from every page, and whether every page was read."""
    found: dict[str, dict[date, _Metrics]] = defaultdict(dict)
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
                    found[entity][day.date] = metrics.metrics
        if page >= answer.metadata.total_pages:
            return found, True
    return found, False


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
    """The tenant's spend per day in the window, each of the named workspaces', and its budget."""
    dates = {
        "start_date": day_of(query.start).isoformat(),
        "end_date": day_of(query.end - timedelta(microseconds=1)).isoformat(),
    }
    tags = {workspace_tag(tenant, workspace): workspace for workspace in query.workspaces}
    days = days_in(query)
    try:
        async with asyncio.timeout(DEADLINE):
            spent, by_team, by_tag = await asyncio.gather(
                litellm.spend(tenant),
                _activity(
                    litellm,
                    "/team/daily/activity",
                    {"team_ids": team(tenant), **dates},
                    {team(tenant)},
                ),
                _activity(
                    litellm, "/tag/daily/activity", {"tags": ",".join(tags), **dates}, set(tags)
                )
                if tags
                else _nothing(),
            )
    except TimeoutError:
        return Ok(data=Usage(days=_days({}, days), workspaces=[], budget=None, complete=False))
    if isinstance(spent, Unavailable):
        return spent
    if isinstance(by_team, Unavailable):
        return by_team
    if isinstance(by_tag, Unavailable):
        return by_tag
    (teams, all_team), (tagged, all_tagged) = by_team, by_tag
    workspaces = [
        WorkspaceSpend(
            workspace=tags[tag],
            spend=sum(metrics.spend for metrics in by_day.values()),
            tokens=sum(metrics.total_tokens for metrics in by_day.values()),
            days=_days(by_day, days),
        )
        for tag, by_day in tagged.items()
    ]
    return Ok(
        data=Usage(
            days=_days(teams.get(team(tenant), {}), days),
            workspaces=sorted(workspaces, key=lambda w: (-w.spend, w.workspace)),
            budget=spent.data,
            complete=all_team and all_tagged,
        )
    )


async def _nothing() -> tuple[dict[str, dict[date, _Metrics]], bool]:
    """No workspaces to ask after: nothing, all of it."""
    return {}, True
