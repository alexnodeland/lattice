"""relayr's telemetry: the bridge's spans, its counters, and where its traces belong.

The follower publishes each bridged event in a span of its own, `relayr.bridge <type>`, linked
to the span that committed the artifactr envelope, so a run in reflexr links back, through it, to
the turn or request behind its event (ADR-0004: traces linked, not continued). It counts the
followers that stop and the envelopes it dead-letters; and, for the tracker connector, the
changes its followers dead-letter or find unannounced, the webhooks it refuses, and the writes
its cap on loops refuses.
"""

from relayr.telemetry.attributes import (
    ENVELOPE_SEQ,
    ERROR_TYPE,
    EVENT_TYPE,
    TENANT_ID,
    WORKSPACE_ID,
)
from relayr.telemetry.metrics import (
    DEAD_LETTERS,
    FOLLOWERS_STOPPED,
    METRICS,
    NUDGES_REFUSED,
    SCOPE,
    SCOPED,
    TRACKER_DEAD_LETTERS,
    TRACKER_LOOPS,
    UNNUDGED,
    Metric,
)
from relayr.telemetry.telemetry import Telemetry, linked, workspace_attributes

__all__ = [
    "DEAD_LETTERS",
    "ENVELOPE_SEQ",
    "ERROR_TYPE",
    "EVENT_TYPE",
    "FOLLOWERS_STOPPED",
    "METRICS",
    "NUDGES_REFUSED",
    "SCOPE",
    "SCOPED",
    "TENANT_ID",
    "TRACKER_DEAD_LETTERS",
    "TRACKER_LOOPS",
    "UNNUDGED",
    "WORKSPACE_ID",
    "Metric",
    "Telemetry",
    "linked",
    "workspace_attributes",
]
