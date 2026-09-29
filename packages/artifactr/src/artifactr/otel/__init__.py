"""OpenTelemetry for applications, in one call: the ``[otel]`` extra.

This package is an adapter (ADR-0034). artifactr records through the OpenTelemetry API, its
port; this package wires the SDK behind it, with OTLP exporters, the open instrumentations and
artifactr's metric cardinality policy::

    telemetry = configure_telemetry(service_name="docplan", environment="production")
    app = create_app()
    telemetry.instrument_app(app)
    agent = Agent(..., capabilities=[ArtifactWorkspace(types=[Doc]), telemetry.capability()])

Nothing in artifactr requires it, and nothing inside artifactr imports it.
"""

from artifactr.otel.configure import (
    BAGGAGE_KEYS,
    INSTRUMENTED,
    Instrumented,
    TelemetryHandle,
    configure_telemetry,
    installed,
    metric_views,
)

__all__ = [
    "BAGGAGE_KEYS",
    "INSTRUMENTED",
    "Instrumented",
    "TelemetryHandle",
    "configure_telemetry",
    "installed",
    "metric_views",
]
