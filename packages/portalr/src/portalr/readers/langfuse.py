"""Langfuse: a tenant's feedback and evaluation scores.

Langfuse is read for scores only; traces come from Tempo. The libraries tag every trace they send
``tenant:<id>``. Langfuse 4's score API neither filters by a trace's tags nor answers with them,
so a read takes two steps, as lattice RFC-0002 allows: the tenant's traces in the window, from
the observations API filtered on the tag, then those traces' scores. Each observation's tags are
checked again, and each score must be on one of those traces.
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


def tenant_tag(tenant: Tenant) -> str:
    """The trace tag that names the tenant: ``tenant:<id>``."""
    return f"tenant:{tenant.id}"


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


class _Observation(BaseModel):
    trace_id: Annotated[str, Field(validation_alias="traceId")]
    tags: list[str] | None = None


class _Observations(BaseModel):
    data: list[_Observation]


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


class _Scores(BaseModel):
    data: list[_Score]


_OBSERVATIONS: Final = TypeAdapter(_Observations)
_SCORES: Final = TypeAdapter(_Scores)


def trace_parameters(tenant: Tenant, window: Window) -> dict[str, str | int]:
    """The observations API's parameters: each root observation in the window that has the tag."""
    conditions = [
        {
            "type": "arrayOptions",
            "column": "traceTags",
            "operator": "all of",
            "value": [tenant_tag(tenant)],
        },
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
        """The tenant's scores in the window, newest first."""
        observed = await read(
            self.client,
            "langfuse",
            f"{self.url}/api/public/v2/observations",
            _OBSERVATIONS,
            params=trace_parameters(tenant, window),
        )
        if observed is None or isinstance(observed, Unavailable):
            return observed or Unavailable(
                reason="langfuse has no observations API at that address"
            )
        if any(observation.tags is None for observation in observed.data):
            return Unavailable(reason="langfuse answered observations without their traces' tags")
        tag = tenant_tag(tenant)
        traces = sorted({o.trace_id for o in observed.data if o.tags and tag in o.tags})
        mine: list[Score] = []
        for at in range(0, len(traces), TRACES_PER_READ):
            batch = traces[at : at + TRACES_PER_READ]
            page = await read(
                self.client,
                "langfuse",
                f"{self.url}/api/public/v3/scores",
                _SCORES,
                params=score_parameters(batch, window),
            )
            if page is None or isinstance(page, Unavailable):
                return page or Unavailable(reason="langfuse has no scores API at that address")
            for score in page.data:
                trace = score.subject.trace if score.subject else None
                if trace is not None and trace in batch:
                    mine.append(Score(trace_id=trace, **score.model_dump(exclude={"subject"})))
        newest = sorted(mine, key=lambda score: score.timestamp, reverse=True)
        return Ok(data=newest[: window.limit])

    def trace_link(self, trace_id: str) -> str:
        """Langfuse's page for a trace."""
        return f"{self.url}/project/{self.project}/traces/{trace_id}"

    def session_link(self, session_id: str) -> str:
        """Langfuse's page for a session: an artifactr thread."""
        return f"{self.url}/project/{self.project}/sessions/{session_id}"
