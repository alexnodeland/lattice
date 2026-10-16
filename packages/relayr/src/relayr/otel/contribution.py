"""relayr's contribution: its scope, its metric views, and its spans' place in traces.

It is a :class:`~lattice_core.otel.contribution.Contribution`, the contract the libraries'
``configure_telemetry`` reads (lattice ADR-0020).
"""

from opentelemetry.sdk.metrics.view import View
from opentelemetry.sdk.trace import ReadableSpan

from lattice_core.otel.contribution import Contribution, MetricsDetail
from relayr.telemetry import METRICS, SCOPE, SCOPED, TENANT_ID

__all__ = ["Contribution", "MetricsDetail", "metric_views", "telemetry"]


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
