"""Langfuse: a tenant's feedback and evaluation scores.

Langfuse is read for scores only; traces come from Tempo. The libraries tag every trace they send
``tenant:<id>``. Langfuse 4's score API neither filters by a trace's tags nor answers with them,
so a read takes two steps, as lattice RFC-0002 allows: the tenant's traces in the window, from
the observations API filtered on the tag, then those traces' scores. Each observation's tags are
checked again, and each score must be on one of those traces. A trace's ``workspace:<id>`` tag,
which artifactr's and reflexr's traces carry, names each score's workspace.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Final, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from portalr.readers.http import read
from portalr.readers.query import Window
from portalr.readers.reading import Ok, Unavailable
from portalr.tenant import Tenant

TRACES_PER_READ: Final = 50
"""How many traces one request for scores names, to keep its URL short."""

MOST_SCORES: Final = 50_000
"""The most scores an aggregate read takes from Langfuse: past it, the read says it is partial."""

TRACES_PER_PAGE: Final = 1000
"""How many traces one page of the observations API returns, the most it allows."""

SCORES_PER_PAGE: Final = 100
"""How many scores one page of the score API returns, the most it allows."""


def tenant_tag(tenant: Tenant) -> str:
    """The trace tag that names the tenant: ``tenant:<id>``."""
    return f"tenant:{tenant.id}"


WORKSPACE_TAG: Final = "workspace:"
"""How a trace's tag names its workspace: ``workspace:<id>``."""


def workspace_of(tags: list[str]) -> str | None:
    """The workspace a trace's tags name, or None for a trace in none, or in more than one."""
    named = {tag.removeprefix(WORKSPACE_TAG) for tag in tags if tag.startswith(WORKSPACE_TAG)}
    return named.pop() if len(named) == 1 else None


class Score(BaseModel):
    """A score: a person's feedback, or an evaluator's verdict, on a trace."""

    model_config = ConfigDict(frozen=True)

    id: str
    trace_id: str
    name: str
    data_type: Literal["NUMERIC", "BOOLEAN", "CATEGORICAL", "TEXT", "CORRECTION"]
    value: float | bool | str
    source: str
    timestamp: datetime
    comment: str | None = None
    evaluator: str | None = None
    """The evaluator that gave it, from evalr's metadata; None for a person's feedback."""
    workspace: str | None = None
    """The workspace its trace is tagged with; None for a trace tagged with none."""


class _Observation(BaseModel):
    trace_id: Annotated[str, Field(validation_alias="traceId")]
    tags: list[str] | None = None


class _Cursor(BaseModel):
    cursor: str | None = None


class _Observations(BaseModel):
    data: list[_Observation]
    meta: _Cursor | None = None


class _Subject(BaseModel):
    kind: str
    id: str
    trace_id: Annotated[str | None, Field(validation_alias="traceId")] = None

    @property
    def trace(self) -> str | None:
        """The trace the score is on, if it is on a trace or one of its observations."""
        return {"trace": self.id, "observation": self.trace_id}.get(self.kind)


class _Score(BaseModel):
    id: str
    name: str
    data_type: Annotated[
        Literal["NUMERIC", "BOOLEAN", "CATEGORICAL", "TEXT", "CORRECTION"],
        Field(validation_alias="dataType"),
    ]
    value: float | bool | str
    source: str
    timestamp: datetime
    comment: str | None = None
    subject: _Subject | None = None
    metadata: dict[str, object] | None = None

    @property
    def evaluator(self) -> str | None:
        """The evaluator evalr names in the score's metadata, if any: a person's has none."""
        named = (self.metadata or {}).get("evaluator")
        return named if isinstance(named, str) else None


class _Scores(BaseModel):
    data: list[_Score]
    meta: _Cursor | None = None


_OBSERVATIONS: Final = TypeAdapter(_Observations)
_SCORES: Final = TypeAdapter(_Scores)


def trace_parameters(
    tenant: Tenant, window: Window, workspace: str | None = None
) -> dict[str, str | int]:
    """The observations API's parameters: each root observation in the window with the tags.

    The tenant's tag, and the workspace's, if one is named.
    """
    tags = [tenant_tag(tenant), *([f"{WORKSPACE_TAG}{workspace}"] if workspace else [])]
    conditions = [
        {"type": "arrayOptions", "column": "traceTags", "operator": "all of", "value": tags},
        {"type": "boolean", "column": "isRootObservation", "operator": "=", "value": True},
        {
            "type": "datetime",
            "column": "startTime",
            "operator": ">=",
            "value": window.start.isoformat(),
        },
        {
            "type": "datetime",
            "column": "startTime",
            "operator": "<",
            "value": window.end.isoformat(),
        },
    ]
    return {
        "fields": "core,trace_context",
        "limit": window.limit,
        "filter": json.dumps(conditions),
    }


def score_parameters(traces: list[str], window: Window) -> dict[str, str | int]:
    """The score API's parameters: these traces' scores in the window, with what they are on."""
    return {
        "traceId": ",".join(traces),
        "fields": "subject,details",
        "fromTimestamp": window.start.isoformat(),
        "toTimestamp": window.end.isoformat(),
        "limit": min(window.limit, 100),
    }


@dataclass(frozen=True)
class Langfuse:
    """Reads scores from Langfuse's public API.

    Args:
        url: Langfuse, such as ``http://langfuse:3000``; also the base of its deep links.
        project: The project's id, for deep links.
        client: The HTTP client, with the project's public and secret keys as its basic auth.
    """

    url: str
    project: str
    client: httpx.AsyncClient = field(default_factory=httpx.AsyncClient)

    async def scores(self, tenant: Tenant, window: Window) -> Ok[list[Score]] | Unavailable:
        """The tenant's scores in the window, newest first, as many as the window's limit."""
        every = await self.every_score(tenant, window)
        if isinstance(every, Unavailable):
            return every
        newest = sorted(every.data, key=lambda score: score.timestamp, reverse=True)
        return Ok(data=newest[: window.limit])

    async def every_score(
        self, tenant: Tenant, window: Window, workspace: str | None = None
    ) -> Ok[list[Score]] | Unavailable:
        """Every score on the tenant's traces in the window, or the workspace's, paged to the end.

        Past ``MOST_SCORES`` it stops, and the read is partial: ``Feedback.complete`` says so.
        """
        workspaces: dict[str, str | None] = {}
        cursor: str | None = None
        while True:
            params = {
                **trace_parameters(tenant, window, workspace),
                "limit": TRACES_PER_PAGE,
                **({"cursor": cursor} if cursor else {}),
            }
            observed = await read(
                self.client,
                "langfuse",
                f"{self.url}/api/public/v2/observations",
                _OBSERVATIONS,
                params=params,
            )
            if observed is None or isinstance(observed, Unavailable):
                return observed or Unavailable(
                    reason="langfuse has no observations API at that address"
                )
            if any(observation.tags is None for observation in observed.data):
                return Unavailable(
                    reason="langfuse answered observations without their traces' tags"
                )
            tag = tenant_tag(tenant)
            workspaces |= {
                o.trace_id: workspace_of(o.tags) for o in observed.data if o.tags and tag in o.tags
            }
            cursor = observed.meta.cursor if observed.meta else None
            if not cursor:
                break
        traces = sorted(workspaces)
        mine: list[Score] = []
        for at in range(0, len(traces), TRACES_PER_READ):
            batch = traces[at : at + TRACES_PER_READ]
            cursor = None
            while len(mine) < MOST_SCORES:
                params = {
                    **score_parameters(batch, window),
                    "limit": SCORES_PER_PAGE,
                    **({"cursor": cursor} if cursor else {}),
                }
                page = await read(
                    self.client,
                    "langfuse",
                    f"{self.url}/api/public/v3/scores",
                    _SCORES,
                    params=params,
                )
                if page is None or isinstance(page, Unavailable):
                    return page or Unavailable(reason="langfuse has no scores API at that address")
                mine += [
                    Score(
                        trace_id=trace,
                        evaluator=score.evaluator,
                        workspace=workspaces[trace],
                        **score.model_dump(exclude={"subject", "metadata"}),
                    )
                    for score in page.data
                    if (trace := score.subject.trace if score.subject else None) in batch
                ]
                cursor = page.meta.cursor if page.meta else None
                if not cursor:
                    break
        return Ok(data=mine)

    def trace_link(self, trace_id: str) -> str:
        """Langfuse's page for a trace."""
        return f"{self.url}/project/{self.project}/traces/{trace_id}"

    def session_link(self, session_id: str) -> str:
        """Langfuse's page for a session: an artifactr thread."""
        return f"{self.url}/project/{self.project}/sessions/{session_id}"
