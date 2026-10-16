"""Prometheus: a tenant's latency and errors over time, through prom-label-proxy.

portalr sends its PromQL to prom-label-proxy, on portalr's path only, with the tenant as the
proxy's ``tenant_id`` parameter. The proxy rewrites every selector to that tenant, so no query
can read another's series; Grafana keeps its direct data source (lattice RFC-0002). Each selector
names the tenant itself too, so a reader pointed at Prometheus directly is still filtered.
"""

import math
from dataclasses import dataclass, field
from typing import Annotated, Final, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from portalr.readers.http import read
from portalr.readers.query import Window, quoted
from portalr.readers.reading import Ok, Unavailable
from portalr.tenant import Tenant

TENANT_LABEL: Final = "tenant_id"
"""The label that names a series' tenant: the collector's ``tenant.id``, as Prometheus spells it,
and the parameter prom-label-proxy enforces it from."""

type Metric = Literal["turn_latency", "failed_turns"]
"""What portalr charts: artifactr's turn latency (p95), and how many turns failed in each step."""

QUERIES: Final[dict[Metric, str]] = {
    "turn_latency": (
        "histogram_quantile(0.95, sum by (le) "
        "(rate(artifactr_turn_duration_seconds_bucket{{{tenant}}}[5m])))"
    ),
    # artifactr records each failed series at zero as a turn starts, so a failure is an increase
    # even when it is the series' first: each point counts the failures in the step before it.
    "failed_turns": (
        'sum(increase(artifactr_turns_total{{artifactr_turn_outcome="failed",{tenant}}}[{step}s]))'
    ),
}
"""Each metric's PromQL, with ``{tenant}`` where its selector names the tenant, and ``{step}``
where it counts over each step."""


def promql(tenant: Tenant, metric: Metric, step: int = 300) -> str:
    """A metric's PromQL, its selector naming the tenant, as the proxy will make sure it does."""
    return QUERIES[metric].format(tenant=f"{TENANT_LABEL}={quoted(tenant.id)}", step=step)


class MetricQuery(Window):
    """A metric over a window, at a step."""

    metric: Metric
    step: Annotated[int, Field(ge=15, le=86_400)] = 300
    """Seconds between points: from 15 to a day."""


class Point(BaseModel):
    """A value at a moment."""

    model_config = ConfigDict(frozen=True)

    time: float
    value: float


class _Series(BaseModel):
    metric: dict[str, str]
    values: list[tuple[float, str]]


class _Data(BaseModel):
    result: list[_Series] = []


class _Answer(BaseModel):
    data: _Data


_ANSWER: Final = TypeAdapter(_Answer)


def parameters(tenant: Tenant, query: MetricQuery) -> dict[str, str | float]:
    """The proxy's parameters for a metric: its PromQL, its window, and the tenant."""
    return {
        "query": promql(tenant, query.metric, query.step),
        "start": query.start.timestamp(),
        "end": query.end.timestamp(),
        "step": query.step,
        TENANT_LABEL: tenant.id,
    }


@dataclass(frozen=True)
class Prometheus:
    """Reads metrics through prom-label-proxy.

    Args:
        url: prom-label-proxy, in front of Prometheus, such as ``http://prom-label-proxy:8080``.
        client: The HTTP client to send requests with.
    """

    url: str
    client: httpx.AsyncClient = field(default_factory=httpx.AsyncClient)

    async def series(self, tenant: Tenant, query: MetricQuery) -> Ok[list[Point]] | Unavailable:
        """The metric over the window: one series, summed over the tenant's."""
        answer = await read(
            self.client,
            "prometheus",
            f"{self.url}/api/v1/query_range",
            _ANSWER,
            params=parameters(tenant, query),
        )
        if answer is None or isinstance(answer, Unavailable):
            return answer or Unavailable(reason="prometheus has no query API at that address")
        # A quantile of nothing is NaN, which is no value: its point is a gap, not a number.
        points = [
            Point(time=time, value=float(value))
            for series in answer.data.result
            for time, value in series.values
            if math.isfinite(float(value))
        ]
        return Ok(data=points)
