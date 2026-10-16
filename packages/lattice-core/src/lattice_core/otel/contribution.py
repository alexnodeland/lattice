"""The contract between a library and ``configure_telemetry``: what a contribution holds.

It needs no extra (lattice ADR-0020). OpenTelemetry's SDK is named in the annotations alone, so
a library's telemetry layer, which records through the API, can import the contract, and a
library's contribution can be built wherever the SDK is installed.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from opentelemetry.sdk.metrics.view import View
    from opentelemetry.sdk.trace import ReadableSpan

__all__ = ["Contribution", "Instrumented", "MetricsDetail", "TelemetryContribution"]

Instrumented = Literal["fastapi", "sqlalchemy", "asyncpg", "httpx"]
"""A library ``configure_telemetry`` can instrument. ``httpx`` covers httpx and httpx2."""

MetricsDetail = Literal["workspace", "tenant", "none"]
"""How much tenancy detail the libraries' metrics keep: part of the contributions' contract."""


class TelemetryContribution(Protocol):
    """What ``configure_telemetry`` reads from a library's contribution: the port.

    It reads these four fields and nothing else, so any value that has them will do: a
    library's own, which no other library imports, or an application's :class:`Contribution`
    for its metrics.
    """

    @property
    def name(self) -> str:
        """The library's name, which is its instrumentation scope; one contribution per name."""
        ...

    @property
    def metric_views(self) -> "Callable[[MetricsDetail], Sequence[View]]":
        """Return the views that apply the library's metric cardinality policy at a detail."""
        ...

    @property
    def should_export_span(self) -> "Callable[[ReadableSpan], bool]":
        """Return whether a span belongs in the library's traces: Langfuse's span filter."""
        ...

    @property
    def instrument(self) -> frozenset[str]:
        """The instrumentations the library advises: those that trace its work.

        Names ``configure_telemetry`` does not know (see :data:`Instrumented`) are ignored.
        """
        ...


@dataclass(frozen=True)
class Contribution:
    """A library's contribution to an application's telemetry.

    Args:
        name: The library's name, which is its instrumentation scope.
        metric_views: Returns the views that keep only the attributes the library's metrics
            may carry at a level of detail.
        should_export_span: Whether a span belongs in the library's traces.
        instrument: The instrumentations the library advises.
    """

    name: str
    metric_views: "Callable[[MetricsDetail], Sequence[View]]"
    should_export_span: "Callable[[ReadableSpan], bool]"
    instrument: frozenset[Instrumented]
