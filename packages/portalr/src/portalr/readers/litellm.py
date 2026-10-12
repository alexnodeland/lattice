"""LiteLLM: a tenant's usage and spend, from its team, and every tenant's, for operators.

Each tenant is a LiteLLM team, ``tenant-<id>``. portalr reads it with the master key, which stays
on the server.
"""

from dataclasses import dataclass, field
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter

from portalr.readers.http import read
from portalr.readers.reading import Ok, Unavailable
from portalr.tenant import Tenant

TEAM_PREFIX: Final = "tenant-"
"""A tenant's team is ``tenant-<id>``."""


def team(tenant: Tenant) -> str:
    """The tenant's LiteLLM team."""
    return f"{TEAM_PREFIX}{tenant.id}"


class Spend(BaseModel):
    """What a tenant has spent, against its budget, if it has one."""

    model_config = ConfigDict(frozen=True)

    spend: float
    max_budget: float | None = None
    budget_duration: str | None = None


class TenantSpend(Spend):
    """A tenant's spend, for operators."""

    tenant: str


class _Team(BaseModel):
    team_id: str
    spend: float = 0
    max_budget: float | None = None
    budget_duration: str | None = None


class _TeamInfo(BaseModel):
    team_info: _Team


_INFO: Final = TypeAdapter(_TeamInfo)
_TEAMS: Final = TypeAdapter(list[_Team])


@dataclass(frozen=True)
class LiteLLM:
    """Reads teams' spend from LiteLLM's admin API.

    Args:
        url: LiteLLM, such as ``http://litellm:4000``.
        client: The HTTP client, with the master key as its bearer token.
    """

    url: str
    client: httpx.AsyncClient = field(default_factory=httpx.AsyncClient)

    async def spend(self, tenant: Tenant) -> Ok[Spend | None] | Unavailable:
        """The tenant's spend; ``None`` if it has no team yet."""
        info = await read(
            self.client, "litellm", f"{self.url}/team/info", _INFO, params={"team_id": team(tenant)}
        )
        if isinstance(info, Unavailable):
            return info
        if info is None:
            return Ok(data=None)
        found = info.team_info
        if found.team_id != team(tenant):
            return Unavailable(reason="litellm answered with another team")
        return Ok(
            data=Spend(
                spend=found.spend,
                max_budget=found.max_budget,
                budget_duration=found.budget_duration,
            )
        )

    async def every_tenant(self) -> Ok[list[TenantSpend]] | Unavailable:
        """Every tenant's spend, from one list of teams, for operators."""
        teams = await read(self.client, "litellm", f"{self.url}/team/list", _TEAMS)
        if teams is None or isinstance(teams, Unavailable):
            return teams or Unavailable(reason="litellm has no team list at that address")
        return Ok(
            data=[
                TenantSpend(
                    tenant=found.team_id.removeprefix(TEAM_PREFIX),
                    spend=found.spend,
                    max_budget=found.max_budget,
                    budget_duration=found.budget_duration,
                )
                for found in teams
                if found.team_id.startswith(TEAM_PREFIX)
            ]
        )
