"""relayr's contribution to an application's telemetry, for the libraries' `configure_telemetry`.

Install `relayr-ai[otel]`, and pass it beside reflexr's:

```python
configure_telemetry(reflexr.otel.telemetry(), relayr.otel.telemetry(), service_name="app")
```

Its span filter keeps relayr's bridge spans in Langfuse's traces, and its views apply the
libraries' cardinality policy to relayr's counters.
"""

from relayr.otel.contribution import Contribution, MetricsDetail, metric_views, telemetry

__all__ = ["Contribution", "MetricsDetail", "metric_views", "telemetry"]
