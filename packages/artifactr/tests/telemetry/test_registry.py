"""The metric registry, its cardinality policy, and recording through the OpenTelemetry API."""

import pytest
from opentelemetry import metrics, trace

from artifactr.core import AgentActor, SystemActor, UserActor
from artifactr.telemetry import (
    EXTERNAL_METRICS,
    METRICS,
    SCOPE,
    SCOPED,
    VERSION,
    Metric,
    MetricsDetail,
    Telemetry,
    annotate,
    attribution,
    continued,
    current_trace_id,
    current_traceparent,
    kept_attributes,
)
from artifactr.telemetry.attributes import (
    ACTOR_KIND,
    ARTIFACT_ID,
    COMMAND_TYPE,
    GEN_AI_CONVERSATION_ID,
    PROPOSAL_ID,
    RUN_ID,
    SESSION_ID,
    TENANT_ID,
    THREAD_ID,
    USER_ID,
    WORKSPACE_ID,
)
from artifactr.telemetry.metrics import COMMANDS, COMMIT_DURATION, STREAM_CONNECTIONS
from tests.telemetry.conftest import Recorder, attributes

IDS = {THREAD_ID, RUN_ID, ARTIFACT_ID, PROPOSAL_ID, SESSION_ID, GEN_AI_CONVERSATION_ID, USER_ID}


@pytest.mark.parametrize("metric", METRICS.values(), ids=lambda m: m.name)
def test_artifactr_metrics_follow_the_cardinality_policy(metric: Metric) -> None:
    assert metric.name.startswith("artifactr.")
    assert metric.scope == SCOPE
    assert metric.description
    assert metric.attributes >= SCOPED, "tenant and workspace are attributes by default"
    assert not metric.attributes & IDS, "ids never become metric attributes"


def test_external_metrics_are_recorded_by_other_scopes() -> None:
    assert all(metric.scope != SCOPE for metric in EXTERNAL_METRICS.values())
    assert not set(METRICS) & set(EXTERNAL_METRICS)


def test_prometheus_names_follow_the_otlp_translation() -> None:
    assert COMMANDS.prometheus_series == {"artifactr_commands_total"}
    assert COMMIT_DURATION.prometheus_series == {
        "artifactr_commit_duration_seconds_bucket",
        "artifactr_commit_duration_seconds_sum",
        "artifactr_commit_duration_seconds_count",
    }
    assert STREAM_CONNECTIONS.prometheus_name == "artifactr_stream_connections"
    assert EXTERNAL_METRICS["operation.cost"].prometheus_name == "operation_cost"
    already = Metric("job.duration_seconds", "histogram", "s", "A name with its unit already.")
    assert already.prometheus_name == "job_duration_seconds"


@pytest.mark.parametrize(
    ("detail", "scoped"),
    [("workspace", SCOPED), ("tenant", {TENANT_ID}), ("none", set[str]())],
)
def test_the_level_of_detail_keeps_tenancy_attributes(
    detail: MetricsDetail, scoped: set[str]
) -> None:
    kept = kept_attributes(COMMANDS, detail)
    assert kept & SCOPED == scoped
    assert COMMAND_TYPE in kept


def test_telemetry_keeps_only_declared_attributes(recorder: Recorder) -> None:
    telemetry = Telemetry(**recorder.providers)
    telemetry.add(COMMANDS, 1, {COMMAND_TYPE: "create_thread", THREAD_ID: "thr_1", USER_ID: None})
    telemetry.add(COMMANDS, 2, {COMMAND_TYPE: "create_thread"})
    telemetry.add(STREAM_CONNECTIONS, 1, {TENANT_ID: "t"})
    telemetry.add(STREAM_CONNECTIONS, -1, {TENANT_ID: "t"})
    telemetry.record(COMMIT_DURATION, 0.5, {COMMAND_TYPE: "create_thread"})
    telemetry.record(COMMIT_DURATION, 0.25, {COMMAND_TYPE: "create_thread"})
    assert recorder.points("artifactr.commands") == [({COMMAND_TYPE: "create_thread"}, 3)]
    assert recorder.points("artifactr.stream.connections") == [({TENANT_ID: "t"}, 0)]
    assert recorder.points("artifactr.commit.duration") == [({COMMAND_TYPE: "create_thread"}, 2)]


def test_telemetry_defaults_to_the_global_providers(
    recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(trace, "get_tracer_provider", lambda: recorder.tracer_provider)
    monkeypatch.setattr(metrics, "get_meter_provider", lambda: recorder.meter_provider)
    telemetry = Telemetry()
    with telemetry.tracer.start_as_current_span("work"):
        telemetry.add(COMMANDS, 1, {})
    span = recorder.span("work")
    assert span.instrumentation_scope is not None
    assert (span.instrumentation_scope.name, span.instrumentation_scope.version) == (
        SCOPE,
        VERSION,
    )
    assert recorder.total("artifactr.commands") == 1


def test_the_current_trace_id_and_annotations(recorder: Recorder) -> None:
    tracer = recorder.tracer_provider.get_tracer("test")
    assert current_trace_id() is None
    annotate({THREAD_ID: "thr_1"})  # nothing is recording: a no-op
    with tracer.start_as_current_span("work") as span:
        trace_id = current_trace_id()
        annotate({THREAD_ID: "thr_1", RUN_ID: None})
    assert trace_id == trace.format_trace_id(span.get_span_context().trace_id)
    assert attributes(recorder.span("work")) == {THREAD_ID: "thr_1"}


def test_the_current_traceparent_is_the_w3c_trace_context(recorder: Recorder) -> None:
    tracer = recorder.tracer_provider.get_tracer("test")
    assert current_traceparent() is None
    with tracer.start_as_current_span("work") as span:
        traceparent = current_traceparent()
    context = span.get_span_context()
    assert traceparent == (
        f"00-{context.trace_id:032x}-{context.span_id:016x}-{context.trace_flags:02x}"
    )


def test_a_block_continued_from_a_traceparent_is_in_its_span(recorder: Recorder) -> None:
    tracer = recorder.tracer_provider.get_tracer("test")
    with tracer.start_as_current_span("request") as request:
        traceparent = current_traceparent()
        with continued(None):
            assert not trace.get_current_span().get_span_context().is_valid, "in no span"
    with continued(traceparent), tracer.start_as_current_span("later"):
        pass
    parent = recorder.span("later").parent
    assert parent is not None
    assert parent.span_id == request.get_span_context().span_id


def test_attribution_names_the_session_the_user_and_the_ids() -> None:
    alice = UserActor(id="alice")
    agent = AgentActor(thread_id="thr_1", run_id="run_1")
    assert attribution(tenant_id="t", workspace_id="w") == {TENANT_ID: "t", WORKSPACE_ID: "w"}
    assert attribution(
        tenant_id="t", workspace_id="w", thread_id="thr_1", run_id="run_1", actor=agent, user=alice
    ) == {
        TENANT_ID: "t",
        WORKSPACE_ID: "w",
        SESSION_ID: "thr_1",
        GEN_AI_CONVERSATION_ID: "thr_1",
        THREAD_ID: "thr_1",
        RUN_ID: "run_1",
        ACTOR_KIND: "agent",
        USER_ID: "alice",
    }
    assert attribution(tenant_id="t", workspace_id="w", actor=alice)[USER_ID] == "alice"
    assert USER_ID not in attribution(tenant_id="t", workspace_id="w", actor=SystemActor())
