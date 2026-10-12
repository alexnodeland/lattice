"""Checks are counted, slow ones traced, and audit entries logged once they commit."""

import logging
from datetime import timedelta

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, NumberDataPoint, Sum
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from grantr.core import TENANT, Forbidden, User
from grantr.grants import Grants, InMemoryStorage
from tests.catalogs import ARTIFACTR

ROOT = User(id="root")


def _counts(reader: InMemoryMetricReader) -> dict[tuple[object, ...], int]:
    data = reader.get_metrics_data()
    assert data is not None
    [metric] = [m for r in data.resource_metrics for s in r.scope_metrics for m in s.metrics]
    assert metric.name == "grantr.checks"
    assert isinstance(metric.data, Sum)
    counts: dict[tuple[object, ...], int] = {}
    for point in metric.data.data_points:
        assert isinstance(point, NumberDataPoint)
        attributes = dict(point.attributes or {})
        key = (
            attributes["grantr.action"],
            attributes["grantr.outcome"],
            attributes.get("grantr.reason"),
        )
        counts[key] = int(point.value)
    return counts


async def test_checks_are_counted_by_action_outcome_and_reason() -> None:
    reader = InMemoryMetricReader()
    grants = Grants(InMemoryStorage(), catalogs=[ARTIFACTR], meter_provider=MeterProvider([reader]))
    await grants.first_operator(ROOT.id)
    await grants.create_tenant("acme", owner="alice", by=ROOT)
    for user in ("alice", "bob"):
        await grants.check("acme", User(id=user), "artifactr:open", TENANT)
    for action in ("artifactr:fly", "artifactr:swim"):
        await grants.check("acme", User(id="alice"), action, TENANT)
    assert _counts(reader) == {
        ("artifactr:open", "allowed", None): 1,
        ("artifactr:open", "refused", "no_grant"): 1,
        ("unknown", "refused", "unknown_action"): 2,
    }


@pytest.mark.parametrize("slow", [True, False])
async def test_only_a_slow_check_is_a_span_with_the_action_as_asked(slow: bool) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    slow_check = timedelta(0) if slow else timedelta(hours=1)
    grants = Grants(InMemoryStorage(), tracer_provider=provider, slow_check=slow_check)
    await grants.check("acme", User(id="bob"), "grantr:read_audit", TENANT)
    await grants.check("acme", User(id="bob"), "grantr:fly", TENANT)
    expected = [
        {
            "grantr.action": action,
            "grantr.outcome": "refused",
            "grantr.reason": reason,
            "grantr.tenant.id": "acme",
        }
        for action, reason in [("grantr:read_audit", "no_grant"), ("grantr:fly", "unknown_action")]
    ]
    finished = exporter.get_finished_spans()
    assert [dict(span.attributes or {}) for span in finished] == (expected if slow else [])
    assert all(span.name == "grantr.check" for span in finished)


async def test_an_audit_entry_is_logged_once_its_change_commits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    grants = Grants(InMemoryStorage())
    with caplog.at_level(logging.INFO, logger="grantr.audit"):
        entry = await grants.first_operator(ROOT.id)
        with pytest.raises(Forbidden):
            await grants.create_tenant("acme", owner="alice", by=User(id="bob"))
    assert [record.getMessage() for record in caplog.records] == [entry.model_dump_json()]
