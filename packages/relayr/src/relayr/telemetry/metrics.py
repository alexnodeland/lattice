"""The metric registry: every metric relayr records, with the attributes it may carry.

Tenant and workspace are attributes, as in the libraries; `relayr.otel.metric_views` drops them
for a deployment that wants fewer series.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from relayr.telemetry.attributes import ERROR_TYPE, EVENT_TYPE, TENANT_ID, WORKSPACE_ID

SCOPE: Final = "relayr"
"""The instrumentation scope of relayr's own spans and metrics."""

SCOPED: Final = frozenset({TENANT_ID, WORKSPACE_ID})
"""The tenancy attributes, which a deployment may drop."""


@dataclass(frozen=True)
class Metric:
    """One counter: what it counts, and the attributes it may carry."""

    name: str
    unit: str
    description: str
    attributes: frozenset[str]


FOLLOWERS_STOPPED: Final = Metric(
    name="relayr.followers.stopped",
    unit="{follower}",
    description="Followers that stopped on an error, until their workspace is opened again",
    attributes=frozenset({TENANT_ID, WORKSPACE_ID, ERROR_TYPE}),
)

DEAD_LETTERS: Final = Metric(
    name="relayr.dead_letters",
    unit="{envelope}",
    description="artifactr envelopes a follower could not bridge, and dead-lettered",
    attributes=frozenset({TENANT_ID, WORKSPACE_ID, EVENT_TYPE}),
)

TRACKER_DEAD_LETTERS: Final = Metric(
    name="relayr.trackers.dead_letters",
    unit="{event}",
    description="Changes in a tracker a follower could not publish, and dead-lettered",
    attributes=frozenset({TENANT_ID, WORKSPACE_ID, EVENT_TYPE}),
)

UNNUDGED: Final = Metric(
    name="relayr.trackers.unnudged",
    unit="{event}",
    description="Changes in a tracker a follower found that no webhook announced",
    attributes=frozenset({TENANT_ID, WORKSPACE_ID}),
)

NUDGES_REFUSED: Final = Metric(
    name="relayr.trackers.nudges_refused",
    unit="{request}",
    description="Webhooks refused, for an unknown tenant or a signature that didn't verify",
    attributes=frozenset(),
)

TRACKER_LOOPS: Final = Metric(
    name="relayr.trackers.loops",
    unit="{write}",
    description="Writes to a tracker's item refused past the cap on writes to one item an hour",
    attributes=frozenset({TENANT_ID, WORKSPACE_ID}),
)

METRICS: Mapping[str, Metric] = MappingProxyType(
    {
        metric.name: metric
        for metric in (
            FOLLOWERS_STOPPED,
            DEAD_LETTERS,
            TRACKER_DEAD_LETTERS,
            UNNUDGED,
            NUDGES_REFUSED,
            TRACKER_LOOPS,
        )
    }
)
"""Every metric relayr records, by name."""
