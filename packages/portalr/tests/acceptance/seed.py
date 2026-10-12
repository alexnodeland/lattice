"""Two tenants' telemetry, sent to the tools as OTLP, already naming ``tenant.id``.

stackr's Collector copies the libraries' tenant attributes to ``tenant.id`` (its smoke test
checks that); here the telemetry names it already, and goes to each tool's own OTLP endpoint.
"""

import os
import time
from typing import Any

import httpx

TENANTS = ("acme", "globex")
SERVICE = "portalr-acceptance"
RUN = f"run-{os.getpid()}-{int(time.time())}"
"""Every seeded record's ``smoke.run``, so a test reads this run's telemetry only."""


def _attributes(**values: str | int) -> list[dict[str, Any]]:
    return [
        {
            "key": key.replace("_", "."),
            "value": {"stringValue": value} if isinstance(value, str) else {"intValue": str(value)},
        }
        for key, value in values.items()
    ]


def _resource() -> dict[str, Any]:
    return {"attributes": _attributes(service_name=SERVICE)}


def _span(
    trace_id: str, span_id: str, tenant: str, now_ns: int, parent: str = ""
) -> dict[str, Any]:
    return {
        "traceId": trace_id,
        "spanId": span_id,
        "parentSpanId": parent,
        "name": f"{tenant} work",
        "kind": 1,
        "startTimeUnixNano": str(now_ns - 1_000_000),
        "endTimeUnixNano": str(now_ns),
        "attributes": [
            {"key": "tenant.id", "value": {"stringValue": tenant}},
            {"key": "smoke.run", "value": {"stringValue": RUN}},
        ],
    }


def trace_ids() -> dict[str, str]:
    """Each seeded trace's id: one per tenant, and one that both tenants' spans share."""
    stamp = f"{int(time.time()):08x}"
    return {
        "acme": f"{stamp}{'a' * 24}",
        "globex": f"{stamp}{'b' * 24}",
        "mixed": f"{stamp}{'c' * 24}",
    }


def seed(tempo_otlp: str, loki: str, prometheus: str) -> dict[str, str]:
    """Send each tenant's trace, logs and failed runs, and a trace both share; return the ids."""
    now = time.time_ns()
    ids = trace_ids()
    spans = [
        _span(ids["acme"], "a" * 16, "acme", now),
        _span(ids["globex"], "b" * 16, "globex", now),
        _span(ids["mixed"], "c" * 16, "acme", now),
        _span(ids["mixed"], "d" * 16, "globex", now, parent="c" * 16),
    ]
    traces = {"resourceSpans": [{"resource": _resource(), "scopeSpans": [{"spans": spans}]}]}
    logs = {
        "resourceLogs": [
            {
                "resource": _resource(),
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "timeUnixNano": str(now),
                                "body": {"stringValue": f"{tenant}'s record {RUN}"},
                                "attributes": [
                                    {"key": "tenant.id", "value": {"stringValue": tenant}},
                                    {"key": "smoke.run", "value": {"stringValue": RUN}},
                                ],
                            }
                            for tenant in TENANTS
                        ]
                    }
                ],
            }
        ]
    }
    # artifactr's failed runs: acme fails once a minute, globex a hundred times.
    points = [
        {
            "timeUnixNano": str(now - minutes * 60_000_000_000),
            "startTimeUnixNano": str(now - 10 * 60_000_000_000),
            "asInt": str((10 - minutes) * (1 if tenant == "acme" else 100)),
            "attributes": [
                {"key": "tenant.id", "value": {"stringValue": tenant}},
                {"key": "artifactr.run.status", "value": {"stringValue": "failed"}},
                {"key": "smoke.run", "value": {"stringValue": RUN}},
            ],
        }
        for tenant in TENANTS
        for minutes in range(9, -1, -1)
    ]
    metrics = {
        "resourceMetrics": [
            {
                "resource": _resource(),
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "artifactr.runs",
                                "unit": "{run}",
                                "sum": {
                                    "dataPoints": points,
                                    "aggregationTemporality": 2,
                                    "isMonotonic": True,
                                },
                            }
                        ]
                    }
                ],
            }
        ]
    }
    with httpx.Client(timeout=10) as client:
        client.post(f"{tempo_otlp}/v1/traces", json=traces).raise_for_status()
        client.post(f"{loki}/otlp/v1/logs", json=logs).raise_for_status()
        client.post(f"{prometheus}/api/v1/otlp/v1/metrics", json=metrics).raise_for_status()
    return ids
