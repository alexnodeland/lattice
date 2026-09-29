"""The metric registry: every metric artifactr records, and the ones its dashboards read.

Each :class:`Metric` declares its name, instrument, unit, description and the attributes it
may carry. artifactr records only declared attributes, so a metric cannot grow an attribute by
accident, and the dashboards in ``deploy/grafana/dashboards/`` are tested against this registry.

The cardinality policy:

- Thread, turn, run, artifact and message ids are never metric attributes. Those granularities
  come from traces.
- Tenant and workspace are attributes by default. :data:`MetricsDetail` names how much of
  that detail to keep, and ``artifactr.otel.metric_views`` turns it into OpenTelemetry views
  that drop the rest before aggregation.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

from artifactr.telemetry.attributes import (
    ACTOR_KIND,
    ARTIFACT_KIND,
    CHANGE,
    CLOSE_CODE,
    COMMAND_TYPE,
    GEN_AI_TOKEN_TYPE,
    GEN_AI_TOOL_NAME,
    OUTCOME,
    PROPOSAL_ACTION,
    REJECTION,
    RUN_STATUS,
    TENANT_ID,
    TOOL_STATUS,
    TURN_OUTCOME,
    TURN_TRIGGER,
    WORKSPACE_ID,
)

Instrument = Literal["counter", "histogram", "up_down_counter"]
"""The kind of OpenTelemetry instrument a metric is recorded with."""

MetricsDetail = Literal["workspace", "tenant", "none"]
"""How much tenancy detail metrics keep: tenant and workspace, the tenant only, or neither."""

SCOPE: Final = "artifactr"
"""The instrumentation scope of artifactr's own spans and metrics."""

SCOPED: Final = frozenset({TENANT_ID, WORKSPACE_ID})
"""The tenancy attributes, which :data:`MetricsDetail` limits."""

_PROMETHEUS_UNITS: Mapping[str, str] = {"s": "seconds", "ms": "milliseconds", "By": "bytes"}


@dataclass(frozen=True)
class Metric:
    """One metric: what it measures, and the attributes it may carry.

    Args:
        name: The OpenTelemetry metric name.
        instrument: The instrument it is recorded with.
        unit: The UCUM unit, or an annotation in braces such as ``{command}``.
        description: What it measures.
        attributes: The attributes it may carry. Anything else is dropped when it is recorded.
        scope: The instrumentation scope that records it: ``artifactr``, or the library whose
            metric a dashboard reads.
        buckets: For a histogram, the bucket boundaries it advises the SDK to use.
    """

    name: str
    instrument: Instrument
    unit: str
    description: str
    attributes: frozenset[str] = frozenset()
    scope: str = SCOPE
    buckets: tuple[float, ...] | None = None

    @property
    def prometheus_name(self) -> str:
        """The metric's name in Prometheus, as the OTLP translation writes it.

        Dots become underscores, a unit of time or size is appended as a word (annotations in
        braces are not), and counters end in ``_total``.
        """
        name = re.sub(r"[^a-zA-Z0-9_:]", "_", self.name)
        unit = _PROMETHEUS_UNITS.get(self.unit, "")
        if unit and not name.endswith(f"_{unit}"):
            name = f"{name}_{unit}"
        return f"{name}_total" if self.instrument == "counter" else name

    @property
    def prometheus_series(self) -> frozenset[str]:
        """Every series name a Prometheus query may use for this metric."""
        name = self.prometheus_name
        if self.instrument == "histogram":
            return frozenset({f"{name}_bucket", f"{name}_sum", f"{name}_count"})
        return frozenset({name})


def _artifactr(
    name: str,
    instrument: Instrument,
    unit: str,
    description: str,
    *attributes: str,
    buckets: tuple[float, ...] | None = None,
) -> Metric:
    return Metric(
        name, instrument, unit, description, frozenset(attributes) | SCOPED, buckets=buckets
    )


COMMANDS = _artifactr(
    "artifactr.commands",
    "counter",
    "{command}",
    "Commands committed through Workspace.commit, by type and outcome.",
    COMMAND_TYPE,
    OUTCOME,
    REJECTION,
    ACTOR_KIND,
)
COMMIT_DURATION = _artifactr(
    "artifactr.commit.duration",
    "histogram",
    "s",
    "How long committing a command took, storage included.",
    COMMAND_TYPE,
    OUTCOME,
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
TURNS = _artifactr(
    "artifactr.turns",
    "counter",
    "{turn}",
    "Turns the Runner handled: a message that started a run, or answers that resumed one.",
    TURN_TRIGGER,
    TURN_OUTCOME,
)
TURN_DURATION = _artifactr(
    "artifactr.turn.duration",
    "histogram",
    "s",
    "How long a turn took, from its start to its end or pause.",
    TURN_TRIGGER,
    TURN_OUTCOME,
    buckets=(0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120, 300, 600),
)
RUNS = _artifactr(
    "artifactr.runs",
    "counter",
    "{run}",
    "Run segments recorded as ended or paused, by status.",
    RUN_STATUS,
)
TOOL_CALLS = _artifactr(
    "artifactr.tool_calls",
    "counter",
    "{call}",
    "Tool calls the agent made, the application's tools included, by tool and status.",
    GEN_AI_TOOL_NAME,
    TOOL_STATUS,
)
TOKENS = _artifactr(
    "artifactr.tokens",
    "counter",
    "{token}",
    "Model tokens that runs used, by type, as recorded when each run segment ends or pauses.",
    GEN_AI_TOKEN_TYPE,
)
MESSAGES = _artifactr(
    "artifactr.messages",
    "counter",
    "{message}",
    "Messages posted in threads, by the kind of actor that posted them.",
    ACTOR_KIND,
)
ARTIFACT_CHANGES = _artifactr(
    "artifactr.artifact.changes",
    "counter",
    "{change}",
    "Artifacts created, changed or archived, by artifact kind and the kind of actor.",
    ARTIFACT_KIND,
    CHANGE,
    ACTOR_KIND,
)
PROPOSALS = _artifactr(
    "artifactr.proposals",
    "counter",
    "{proposal}",
    "Proposals created, accepted and rejected, by the kind of actor.",
    PROPOSAL_ACTION,
    ACTOR_KIND,
)
STREAM_CONNECTIONS = _artifactr(
    "artifactr.stream.connections",
    "up_down_counter",
    "{connection}",
    "Open thread-protocol WebSocket connections.",
)
STREAM_DISCONNECTS = _artifactr(
    "artifactr.stream.disconnects",
    "counter",
    "{connection}",
    "Thread-protocol WebSocket connections that ended, by close code.",
    CLOSE_CODE,
)

METRICS: Mapping[str, Metric] = MappingProxyType(
    {
        metric.name: metric
        for metric in (
            COMMANDS,
            COMMIT_DURATION,
            TURNS,
            TURN_DURATION,
            RUNS,
            TOOL_CALLS,
            TOKENS,
            MESSAGES,
            ARTIFACT_CHANGES,
            PROPOSALS,
            STREAM_CONNECTIONS,
            STREAM_DISCONNECTS,
        )
    }
)
"""artifactr's own metrics, by name."""

EXTERNAL_METRICS: Mapping[str, Metric] = MappingProxyType(
    {
        metric.name: metric
        for metric in (
            Metric(
                "gen_ai.client.token.usage",
                "histogram",
                "{token}",
                "Tokens per model request, by model and type.",
                scope="pydantic-ai",
            ),
            Metric(
                "operation.cost",
                "histogram",
                "{USD}",
                "Estimated cost per model request, by model.",
                scope="pydantic-ai",
            ),
            Metric(
                "gen_ai.client.operation.time_to_first_chunk",
                "histogram",
                "s",
                "Time to the first chunk of a streamed model response.",
                scope="pydantic-ai",
            ),
            Metric(
                "http.server.request.duration",
                "histogram",
                "s",
                "HTTP requests served, REST and MCP.",
                scope="opentelemetry.instrumentation.fastapi",
            ),
            Metric(
                "http.server.active_requests",
                "up_down_counter",
                "{request}",
                "HTTP requests in progress.",
                scope="opentelemetry.instrumentation.fastapi",
            ),
            Metric(
                "http.client.request.duration",
                "histogram",
                "s",
                "Outgoing HTTP requests, model providers included.",
                scope="opentelemetry.instrumentation.httpx",
            ),
            Metric(
                "db.client.connections.usage",
                "up_down_counter",
                "{connection}",
                "Database connections in the pool, by state.",
                scope="opentelemetry.instrumentation.sqlalchemy",
            ),
        )
    }
)
"""Metrics recorded by pydantic-ai and the OpenTelemetry instrumentations that artifactr's
dashboards read, by name. The HTTP metrics are the stable HTTP conventions' names."""


def kept_attributes(metric: Metric, detail: MetricsDetail) -> frozenset[str]:
    """Return the attributes of ``metric`` that a deployment keeps at a level of detail."""
    dropped = {"workspace": set[str](), "tenant": {WORKSPACE_ID}, "none": set(SCOPED)}[detail]
    return metric.attributes - dropped
