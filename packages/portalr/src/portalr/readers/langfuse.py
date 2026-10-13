"""Langfuse: a tenant's feedback and evaluation scores.

Langfuse is read for scores only; traces come from Tempo. The libraries tag every trace they send
``tenant:<id>``. Langfuse 4's score API neither filters by a trace's tags nor answers with them,
so a read takes two steps, as lattice RFC-0002 allows: the tenant's traces in the window, from
the observations API filtered on the tag, then those traces' scores. Each observation's tags are
checked again, and each score must be on one of those traces. A trace's ``workspace:<id>`` tag,
which artifactr's and reflexr's traces carry, names each score's workspace.

A read is bounded: so many pages of traces, so many scores, so long in all; past any bound, it
answers what it read, and says it is partial (portalr ADR-0027).
"""

import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Annotated, Final, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from portalr.readers.http import read
from portalr.readers.query import Span, Window
from portalr.readers.reading import Ok, Unavailable
from portalr.tenant import Tenant

TRACES_PER_READ: Final = 50
"""How many traces one request for scores names, to keep its URL short."""

MOST_SCORES: Final = 50_000
"""The most scores a read takes from Langfuse: past it, the read is partial."""

TRACES_PER_PAGE: Final = 1000
"""How many traces one page of the observations API returns, the most it allows."""

MOST_TRACE_PAGES: Final = 20
"""The most pages of traces a read takes, 20,000 traces: past it, the read is partial."""

SCORES_PER_PAGE: Final = 100
"""How many scores one page of the score API returns, the most it allows."""

BATCHES_AT_ONCE: Final = 4
"""How many requests for scores a read has open at once."""

DEADLINE: Final = 20.0
"""How long a read may take, in seconds: past it, the read answers what it has, partial."""

LOOKBACK: Final = timedelta(days=7)
"""How far before a window a trace may start and still be scored in it: a late thumb, or an
evaluator's verdict on yesterday's turn, is counted on the day it was given."""


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
    feedback_type: str | None = None
    """The feedback type a person's score came from, such as ``thumbs``, from the mirror's
    metadata; None for an evaluator's."""
    workspace: str | None = None
    """The workspace its trace is tagged with; None for a trace tagged with none."""


class _Observation(BaseModel):
    trace_id: Annotated[str, Field(validation_alias="traceId")]
    start: Annotated[datetime, Field(validation_alias="startTime")]
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

    @property
    def feedback_type(self) -> str | None:
        """The feedback type the libraries' mirrors name in a person's score's metadata, if any."""
        named = (self.metadata or {}).get("feedback_type")
        return named if isinstance(named, str) else None


class _Scores(BaseModel):
    data: list[_Score]
    meta: _Cursor | None = None


_OBSERVATIONS: Final = TypeAdapter(_Observations)
_SCORES: Final = TypeAdapter(_Scores)


def trace_parameters(tenant: Tenant, span: Span, workspace: str | None = None) -> dict[str, str]:
    """The observations API's parameters: each root observation with the tags that may be scored.

    A trace may be scored in the span if it started in it or up to ``LOOKBACK`` before it. The
    tags are the tenant's, and the workspace's, if one is named.
    """
    tags = [tenant_tag(tenant), *([f"{WORKSPACE_TAG}{workspace}"] if workspace else [])]
    conditions = [
        {"type": "arrayOptions", "column": "traceTags", "operator": "all of", "value": tags},
        {"type": "boolean", "column": "isRootObservation", "operator": "=", "value": True},
        {
            "type": "datetime",
            "column": "startTime",
            "operator": ">=",
            "value": (span.start - LOOKBACK).isoformat(),
        },
        {"type": "datetime", "column": "startTime", "operator": "<", "value": span.end.isoformat()},
    ]
    return {"fields": "core,trace_context", "filter": json.dumps(conditions)}


def score_parameters(traces: list[str], span: Span) -> dict[str, str]:
    """The score API's parameters: these traces' scores in the span, with what they are on."""
    return {
        "traceId": ",".join(traces),
        "fields": "subject,details",
        "fromTimestamp": span.start.isoformat(),
        "toTimestamp": span.end.isoformat(),
    }


class Scores(BaseModel):
    """The scores a read took, whether they are all there were, and since when they are known."""

    model_config = ConfigDict(frozen=True)

    scores: list[Score]
    complete: bool
    known_from: datetime | None = None
    """Where a read stopped short of the oldest traces: the start of the oldest it read. Before
    it, scores are unknown, not none. None when every trace was read."""


@dataclass
class _Traces:
    """A tenant's traces, each with when it started and its workspace, and whether all were read.

    ``oldest`` is the start of the oldest trace read, and ``ordered`` whether Langfuse sent them
    newest first, as each read assumes and checks.
    """

    found: dict[str, tuple[datetime, str | None]]
    complete: bool
    oldest: datetime | None = None
    ordered: bool = True

    def known_from(self, span: Span) -> datetime | None:
        """Since when the traces are all read: None if they all were.

        Else from the oldest read; or from the span's end, knowing none of it, if they weren't
        sent newest first.
        """
        if self.complete:
            return None
        return self.oldest if self.ordered and self.oldest is not None else span.end


class _Stop(Exception):
    """A batch of scores was refused: raised in its task so the task group cancels the others."""


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

    async def scores(self, tenant: Tenant, window: Window) -> Ok[Scores] | Unavailable:
        """The tenant's scores in the window, sorted newest first, as many as the window's limit.

        Its newest traces' scores are asked for first, but several batches at once, so a read
        that stops at the limit holds scores from about its newest traces, not strictly the
        newest scores; it says it is partial.
        """
        every = await self.every_score(tenant, window, most=window.limit)
        if isinstance(every, Unavailable):
            return every
        newest = sorted(every.data.scores, key=lambda score: score.timestamp, reverse=True)
        return Ok(data=every.data.model_copy(update={"scores": newest[: window.limit]}))

    async def every_score(
        self,
        tenant: Tenant,
        span: Span,
        workspace: str | None = None,
        *,
        most: int = MOST_SCORES,
    ) -> Ok[Scores] | Unavailable:
        """The scores given in the span on the tenant's traces, or the workspace's, up to `most`.

        Its traces are those started up to ``LOOKBACK`` before the span, newest first, read so
        many pages at most; their scores are read ``BATCHES_AT_ONCE`` requests at a time, each
        paged to its end. Past a bound, or the ``DEADLINE``, it answers what it read, partial.
        """
        found: dict[str, Score] = {}
        traced: _Traces | Unavailable | None = None
        known_from: datetime | None = None
        try:
            async with asyncio.timeout(DEADLINE):
                traced = await self._traces(tenant, span, workspace)
                if isinstance(traced, Unavailable):
                    return traced
                read = traced
                known_from = read.known_from(span)
                newest = sorted(read.found, key=lambda trace: read.found[trace][0], reverse=True)
                gate = asyncio.Semaphore(BATCHES_AT_ONCE)
                refused: list[Unavailable] = []

                async def batch(traces: list[str]) -> bool:
                    async with gate:
                        if len(found) >= most:
                            return False
                        scored = await self._scores_of(traces, read, span, found, most)
                        if isinstance(scored, Unavailable):
                            refused.append(scored)
                            raise _Stop
                        return scored

                tasks: list[asyncio.Task[bool]] = []
                with contextlib.suppress(_Stop):
                    async with asyncio.TaskGroup() as group:
                        tasks.extend(
                            group.create_task(batch(newest[at : at + TRACES_PER_READ]))
                            for at in range(0, len(newest), TRACES_PER_READ)
                        )
                if refused:
                    return refused[0]
                complete = read.complete and all(task.result() for task in tasks)
        except TimeoutError:
            if not isinstance(traced, _Traces):
                return Unavailable(reason="langfuse didn't answer in time")
            complete = False
        return Ok(
            data=Scores(
                scores=list(found.values())[:most],
                complete=complete and len(found) < most,
                known_from=known_from,
            )
        )

    async def _traces(
        self, tenant: Tenant, span: Span, workspace: str | None
    ) -> _Traces | Unavailable:
        """The tenant's traces that may be scored in the span, newest first, so many pages."""
        tag = tenant_tag(tenant)
        traces = _Traces(found={}, complete=True)
        cursor: str | None = None
        seen: set[str] = set()
        for _ in range(MOST_TRACE_PAGES):
            params = {
                **trace_parameters(tenant, span, workspace),
                "limit": str(TRACES_PER_PAGE),
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
            # Langfuse sends the newest first, though it doesn't promise to: checked as read.
            for observation in observed.data:
                if traces.oldest is not None and observation.start > traces.oldest:
                    traces.ordered = False
                traces.oldest = min(traces.oldest or observation.start, observation.start)
            # Each trace's tags checked again: the tenant's, and the workspace's, if one is named.
            traces.found |= {
                o.trace_id: (o.start, workspace_of(o.tags))
                for o in observed.data
                if o.tags
                and tag in o.tags
                and (workspace is None or workspace_of(o.tags) == workspace)
            }
            cursor = observed.meta.cursor if observed.meta else None
            if not cursor:
                return traces
            if cursor in seen:
                # A page that sends back to one already read: what was read is what there is.
                traces.complete = False
                return traces
            seen.add(cursor)
        traces.complete = False
        return traces

    async def _scores_of(
        self, batch: list[str], traced: _Traces, span: Span, found: dict[str, Score], most: int
    ) -> bool | Unavailable:
        """The batch's scores in the span, paged to the end or to `most`, added to `found` by id.

        True if it read them all; False if it stopped at `most`, or at a page it had read.
        """
        cursor: str | None = None
        seen: set[str] = set()
        while len(found) < most:
            params = {
                **score_parameters(batch, span),
                "limit": str(SCORES_PER_PAGE),
                **({"cursor": cursor} if cursor else {}),
            }
            page = await read(
                self.client, "langfuse", f"{self.url}/api/public/v3/scores", _SCORES, params=params
            )
            if page is None or isinstance(page, Unavailable):
                return page or Unavailable(reason="langfuse has no scores API at that address")
            found |= {
                score.id: Score(
                    trace_id=trace,
                    evaluator=score.evaluator,
                    feedback_type=score.feedback_type,
                    workspace=traced.found[trace][1],
                    **score.model_dump(exclude={"subject", "metadata"}),
                )
                for score in page.data
                if (trace := score.subject.trace if score.subject else None) in batch
            }
            cursor = page.meta.cursor if page.meta else None
            if not cursor:
                return True
            if cursor in seen:
                # A page that sends back to one already read: what was read is what there is.
                return False
            seen.add(cursor)
        return False

    def trace_link(self, trace_id: str) -> str:
        """Langfuse's page for a trace."""
        return f"{self.url}/project/{self.project}/traces/{trace_id}"

    def session_link(self, session_id: str) -> str:
        """Langfuse's page for a session: an artifactr thread."""
        return f"{self.url}/project/{self.project}/sessions/{session_id}"
