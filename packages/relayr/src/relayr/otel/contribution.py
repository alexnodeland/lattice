"""relayr's contribution: its scope, its metric views, and its spans' place in traces."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from opentelemetry.sdk.metrics.view import View
from opentelemetry.sdk.trace import ReadableSpan

from relayr.telemetry import METRICS, SCOPE, SCOPED, TENANT_ID

MetricsDetail = Literal["workspace", "tenant", "none"]
"""How much tenancy detail metrics keep, as the libraries' `MetricsDetail` says."""


@dataclass(frozen=True)
class Contribution:
    """What the libraries' `configure_telemetry` reads from a contribution (artifactr ADR-0046).

    Args:
        name: The instrumentation scope.
        metric_views: Returns the views that keep only the attributes allowed at a detail.
        should_export_span: Whether a span belongs in relayr's traces.
        instrument: The instrumentations relayr advises: none of its own.
    """

    name: str
    metric_views: Callable[[MetricsDetail], Sequence[View]]
    should_export_span: Callable[[ReadableSpan], bool]
    instrument: frozenset[str]


def telemetry() -> Contribution:
    """Return relayr's contribution, for either library's `configure_telemetry`."""
    return Contribution(
        name=SCOPE,
        metric_views=metric_views,
        should_export_span=_in_relayrs_traces,
        instrument=frozenset(),
    )


def metric_views(detail: MetricsDetail = "workspace") -> list[View]:
    """Return views that keep only the attributes relayr's counters may carry at `detail`.

    With `"tenant"` the workspace is dropped, and with `"none"` both tenant and workspace are.
    """
    dropped = {"workspace": frozenset[str](), "tenant": SCOPED - {TENANT_ID}, "none": SCOPED}
    return [
        View(
            instrument_name=metric.name,
            meter_name=SCOPE,
            attribute_keys=set(metric.attributes - dropped[detail]),
        )
        for metric in METRICS.values()
    ]


def _in_relayrs_traces(span: ReadableSpan) -> bool:
    return span.instrumentation_scope is not None and span.instrumentation_scope.name == SCOPE
