"""Recording spans and metrics through the OpenTelemetry API.

The API is the port: artifactr records through it and never configures the SDK. With no SDK
configured, everything here is a no-op.
"""

import contextlib
from collections.abc import Generator, Iterable, Mapping
from importlib.metadata import version
from typing import Final

from opentelemetry import context as otel_context
from opentelemetry import metrics, trace
from opentelemetry.metrics import Counter, Histogram, MeterProvider, UpDownCounter
from opentelemetry.trace import Span, TracerProvider
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.util.types import AttributeValue

from artifactr.core import (
    Actor,
    ArtifactArchived,
    ArtifactChanged,
    ArtifactCreated,
    FeedbackGiven,
    KnownEvent,
    MessagePosted,
    ProposalCreated,
    ProposalResolved,
    RunEnded,
    RunPaused,
    RunUsage,
    ToolReturned,
    TraceId,
)
from artifactr.telemetry.attributes import (
    ACTOR_KIND,
    ARTIFACT_KIND,
    CHANGE,
    FEEDBACK_TARGET,
    FEEDBACK_TYPE,
    GEN_AI_TOKEN_TYPE,
    GEN_AI_TOOL_NAME,
    MESSAGE_KIND,
    PROPOSAL_ACTION,
    RUN_REASON,
    RUN_STATUS,
    TOOL_STATUS,
)
from artifactr.telemetry.metrics import (
    ARTIFACT_CHANGES,
    FEEDBACK,
    MESSAGES,
    PROPOSALS,
    RUNS,
    SCOPE,
    TOKENS,
    TOOL_CALLS,
    Metric,
)

VERSION: Final = version("artifactr-ai")
"""The version recorded with artifactr's instrumentation scope."""

type Attributes = Mapping[str, AttributeValue | None]

_W3C = TraceContextTextMapPropagator()


class Telemetry:
    """The tracer and meter one artifactr component records with.

    ``Workspaces``, ``Runner`` and the surfaces each hold one, built from the providers they
    are given, or the global ones. Metrics are recorded only through :meth:`add` and
    :meth:`record`, which keep just the attributes the metric declares.

    Args:
        tracer_provider: Where spans go. Defaults to the global tracer provider.
        meter_provider: Where metrics go. Defaults to the global meter provider.
    """

    def __init__(
        self,
        *,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
    ) -> None:
        tracer_provider = tracer_provider or trace.get_tracer_provider()
        meter_provider = meter_provider or metrics.get_meter_provider()
        self.tracer = tracer_provider.get_tracer(SCOPE, VERSION)
        """The tracer for artifactr's spans."""
        self.meter = meter_provider.get_meter(SCOPE, VERSION)
        """The meter for artifactr's metrics."""
        self._counters: dict[str, Counter | UpDownCounter] = {}
        self._histograms: dict[str, Histogram] = {}

    def add(self, metric: Metric, amount: int, attributes: Attributes) -> None:
        """Add to a counter or an up-down counter."""
        if (counter := self._counters.get(metric.name)) is None:
            create = (
                self.meter.create_up_down_counter
                if metric.instrument == "up_down_counter"
                else self.meter.create_counter
            )
            counter = self._counters[metric.name] = create(
                metric.name, metric.unit, metric.description
            )
        counter.add(amount, _kept(metric, attributes))

    def record(self, metric: Metric, value: float, attributes: Attributes) -> None:
        """Record a value in a histogram."""
        if (histogram := self._histograms.get(metric.name)) is None:
            histogram = self._histograms[metric.name] = self.meter.create_histogram(
                metric.name,
                metric.unit,
                metric.description,
                explicit_bucket_boundaries_advisory=metric.buckets,
            )
        histogram.record(value, _kept(metric, attributes))


def _kept(metric: Metric, attributes: Attributes) -> dict[str, AttributeValue]:
    return {
        key: value
        for key, value in attributes.items()
        if key in metric.attributes and value is not None
    }


def current_trace_id() -> TraceId | None:
    """Return the id of the current trace, or None when nothing is being traced."""
    context = trace.get_current_span().get_span_context()
    return trace.format_trace_id(context.trace_id) if context.is_valid else None


def current_traceparent() -> str | None:
    """Return the W3C trace context of the current span, if there is one."""
    carrier: dict[str, str] = {}
    _W3C.inject(carrier)
    return carrier.get("traceparent")


@contextlib.contextmanager
def continued(traceparent: str | None) -> Generator[None]:
    """Run a block as if in the span a W3C ``traceparent`` names, such as an envelope's.

    What the block starts is that span's: its child, or a turn linked to it. With no
    ``traceparent``, the block is in no span.
    """
    carrier = {} if traceparent is None else {"traceparent": traceparent}
    token = otel_context.attach(_W3C.extract(carrier))
    try:
        yield
    finally:
        otel_context.detach(token)


def annotate(attributes: Attributes, span: Span | None = None) -> None:
    """Set attributes on a span (the current one by default), skipping None values."""
    target = span or trace.get_current_span()
    if target.is_recording():
        target.set_attributes({k: v for k, v in attributes.items() if v is not None})


def record_events(
    telemetry: Telemetry, events: Iterable[KnownEvent], *, actor: Actor, scope: Attributes
) -> None:
    """Count what a batch of committed events did.

    Args:
        telemetry: Where to record.
        events: The events one command or fact appended.
        actor: Who committed them.
        scope: The tenancy attributes (tenant and workspace).
    """
    by_actor = {**scope, ACTOR_KIND: actor.kind}
    for event in events:
        match event:
            case MessagePosted():
                telemetry.add(MESSAGES, 1, {**by_actor, MESSAGE_KIND: event.kind})
            case ArtifactCreated() | ArtifactChanged() | ArtifactArchived():
                change = event.type.removeprefix("artifact_")
                attributes = {**by_actor, ARTIFACT_KIND: event.kind, CHANGE: change}
                telemetry.add(ARTIFACT_CHANGES, 1, attributes)
            case ProposalCreated():
                telemetry.add(PROPOSALS, 1, {**by_actor, PROPOSAL_ACTION: "created"})
            case ProposalResolved():
                action = "accepted" if event.decision == "accept" else "rejected"
                telemetry.add(PROPOSALS, 1, {**by_actor, PROPOSAL_ACTION: action})
            case ToolReturned():
                attributes = {**scope, GEN_AI_TOOL_NAME: event.tool_name, TOOL_STATUS: event.status}
                telemetry.add(TOOL_CALLS, 1, attributes)
            case RunPaused():
                telemetry.add(RUNS, 1, {**scope, RUN_STATUS: "paused"})
                _tokens(telemetry, event.usage, scope)
            case RunEnded():
                ended = {**scope, RUN_STATUS: event.status, RUN_REASON: event.reason}
                telemetry.add(RUNS, 1, ended)
                _tokens(telemetry, event.usage, scope)
            case FeedbackGiven():
                attributes = {
                    **by_actor,
                    FEEDBACK_TYPE: event.feedback_type,
                    FEEDBACK_TARGET: event.target.kind,
                }
                telemetry.add(FEEDBACK, 1, attributes)
            case _:
                pass


def _tokens(telemetry: Telemetry, usage: RunUsage | None, scope: Attributes) -> None:
    if usage is None:
        return
    for token_type, count in (("input", usage.input_tokens), ("output", usage.output_tokens)):
        if count:
            telemetry.add(TOKENS, count, {**scope, GEN_AI_TOKEN_TYPE: token_type})
