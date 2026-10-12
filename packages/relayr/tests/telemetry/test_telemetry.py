"""relayr's counters, its contribution to an application's telemetry, and its Langfuse tags."""

import logging
from datetime import timedelta
from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider

import artifactr.core as a
import reflexr
from relayr.events import BRIDGED, MessagePosted, Projections
from relayr.ledger import Cause, Ledger
from relayr.otel import MetricsDetail, metric_views, telemetry
from relayr.telemetry import (
    DEAD_LETTERS,
    EVENT_TYPE,
    SCOPE,
    TENANT_ID,
    WORKSPACE_ID,
    Telemetry,
    linked,
    workspace_attributes,
)
from tests.app_types import Note
from tests.clock import FakeClock
from tests.stack import ALICE, KEY, Stack, until


def counted(reader: InMemoryMetricReader) -> dict[str, list[dict[str, Any]]]:
    """Each counter's points' attributes, by name."""
    found: dict[str, list[dict[str, Any]]] = {}
    data = reader.get_metrics_data()
    for resource in data.resource_metrics if data else ():
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                found[metric.name] = [dict(p.attributes or {}) for p in metric.data.data_points]
    return found


def refuse(envelope: a.Envelope) -> reflexr.Event | None:
    raise ValueError("no")


async def test_dead_letters_and_stopped_followers_are_counted(
    ledger: Ledger, stack: Stack, caplog: pytest.LogCaptureFixture
) -> None:
    reader = InMemoryMetricReader()
    app = stack.process(
        ledger,
        projections=Projections(artifacts={"note": refuse}),
        events=tuple(t for t in BRIDGED if t is not MessagePosted),
        rules=[],
        meter_provider=MeterProvider(metric_readers=[reader]),
    )
    alice = await app.collaboration.open(*KEY, actor=ALICE)
    await alice.create(Note(text=""))
    with caplog.at_level(logging.ERROR, logger="relayr.inbound"):
        thread = await alice.create_thread()
        await alice.post_message(thread.id, "hello")

        async def stopped() -> bool:
            return "relayr.followers.stopped" in counted(reader)

        await until(stopped)
    found = counted(reader)
    workspace = {"relayr.tenant.id": "acme", "relayr.workspace.id": "prod"}
    assert found["relayr.dead_letters"] == [{**workspace, "relayr.event.type": "artifact_created"}]
    assert found["relayr.followers.stopped"] == [{**workspace, "error.type": "NotFound"}]


async def test_a_follower_forgets_old_causes_while_it_holds_its_lease(
    ledger: Ledger, stack: Stack, clock: FakeClock
) -> None:
    cause = Cause(correlation_id="evt_1", firing_id="fir_1", run_id="fir_1", depth=1)
    await ledger.record_cause(KEY, "message", "msg_old", cause)
    clock.advance(timedelta(seconds=1))
    app = stack.process(ledger, cause_ttl=timedelta(0))
    alice = await app.collaboration.open(*KEY, actor=ALICE)
    del alice

    async def forgotten() -> bool:
        return await ledger.cause(KEY, "message", "msg_old") is None

    await until(forgotten)
    await ledger.record_cause(KEY, "message", "msg_later", cause)
    clock.advance(timedelta(seconds=1))

    async def forgotten_again() -> bool:
        return await ledger.cause(KEY, "message", "msg_later") is None

    await until(forgotten_again)


@pytest.mark.parametrize(
    "traceparent",
    [None, "00-00000000000000000000000000000000-0000000000000000-01", "garbled"],
)
def test_nothing_is_linked_without_a_valid_traceparent(traceparent: str | None) -> None:
    assert linked(traceparent) == []


def test_relayrs_contribution_keeps_its_spans() -> None:
    contribution = telemetry()
    assert (contribution.name, contribution.instrument) == (SCOPE, frozenset())
    provider = TracerProvider()
    with provider.get_tracer(SCOPE).start_as_current_span("relayr.bridge x") as ours:
        pass
    with provider.get_tracer("other").start_as_current_span("other") as theirs:
        pass
    assert isinstance(ours, ReadableSpan)
    assert isinstance(theirs, ReadableSpan)
    assert contribution.should_export_span(ours)
    assert not contribution.should_export_span(theirs)


@pytest.mark.parametrize(
    ("detail", "kept"),
    [
        ("workspace", {TENANT_ID, WORKSPACE_ID, EVENT_TYPE}),
        ("tenant", {TENANT_ID, EVENT_TYPE}),
        ("none", {EVENT_TYPE}),
    ],
)
def test_relayrs_views_keep_as_much_tenancy_as_asked(detail: MetricsDetail, kept: set[str]) -> None:
    reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[reader], views=metric_views(detail))
    recording = Telemetry(meter_provider=meters)
    recording.count(
        DEAD_LETTERS,
        {**workspace_attributes("acme", "prod"), EVENT_TYPE: "app_event", "extra": "dropped"},
    )
    [point] = counted(reader)["relayr.dead_letters"]
    assert set(point) == kept
