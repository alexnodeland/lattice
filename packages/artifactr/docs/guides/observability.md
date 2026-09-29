# Observability

artifactr traces every turn, command, agent run and tool call, and counts what happens in each workspace, through the OpenTelemetry API ([ADR-0027](../adr/0027-opentelemetry-observability-with-langfuse.md)). It never configures OpenTelemetry itself: until your application sets up the SDK, recording costs nothing and goes nowhere. This page shows what is recorded and how to turn it on.

## Turning it on

Configure the OpenTelemetry SDK once, when the application starts, and give pydantic-ai's `Instrumentation` capability to your agent so its runs, model requests and tool calls are traced too:

```python
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic_ai import Agent
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.models.instrumented import InstrumentationSettings

tracer_provider = TracerProvider()
tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
meter_provider = MeterProvider(metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())])
trace.set_tracer_provider(tracer_provider)
metrics.set_meter_provider(meter_provider)

agent = Agent(
    "anthropic:claude-sonnet-5-5",
    deps_type=Session[AppDeps],
    capabilities=[
        ArtifactWorkspace(types=[Doc, Plan]),
        Instrumentation(settings=InstrumentationSettings(include_content=False)),
    ],
)
```

`Workspaces`, `Runner` and `artifactr_router` use the global providers. To keep artifactr's telemetry apart, pass `tracer_provider=` and `meter_provider=` to each instead. Never call `Agent.instrument_all()` from a library; it instruments every agent in the process.

## Traces

A **turn** is one trace ([ADR-0035](../adr/0035-a-turn-is-its-own-trace.md)). When a message starts a run, or answers resume one, the `Runner` starts an `invoke_workflow turn` span as the root of a new trace, linked to the span that was current when the message arrived (the REST request, say). Inside it:

```text
invoke_workflow turn                  the Runner
└── invoke_agent agent                pydantic-ai, with artifactr's attribution
    ├── chat claude-sonnet-5-5        pydantic-ai: one per model request
    ├── execute_tool edit_text        pydantic-ai, with artifactr.artifact.id
    │   └── artifactr.commit edit_artifact
    └── artifactr.commit post_message the agent's reply
```

Commands from people are traced where they arrive: `artifactr.commit {type}` inside the REST request's span or the WebSocket connection's `artifactr.stream` span.

Every span artifactr owns or wraps says who and where:

| Attribute | Value |
|---|---|
| `session.id`, `gen_ai.conversation.id`, `artifactr.thread.id` | The thread id: the thread is the session |
| `user.id` | The person's id, for a person's commands and the turns they start |
| `artifactr.tenant.id`, `artifactr.workspace.id` | The tenancy |
| `artifactr.run.id` | artifactr's run id, which spans pauses; pydantic-ai's own run id is per attempt |
| `artifactr.actor.kind` | `user`, `agent`, `external_agent` or `system` |

artifactr's spans carry ids, kinds, versions and counts, never content. Prompts, messages and tool arguments appear only on pydantic-ai's spans, and only when its `include_content` is on.

Each run records the trace of each attempt in `Run.trace_ids`, and each revision the trace it was committed in, so feedback can be attached to the trace it is about.

## Metrics

artifactr's metrics are declared in a registry, `artifactr.telemetry.METRICS`, with the attributes each may carry. The [architecture](../architecture.md#metrics) lists them: commands and commit latency, turns and turn latency, runs by status, tool calls by tool and status, tokens, messages, artifact changes, proposals, and WebSocket connections.

Thread, run, artifact and message ids are never metric attributes; they are in the traces. Tenant and workspace are attributes by default, which suits most deployments. With many workspaces, drop them from metrics with OpenTelemetry views; the registry's `kept_attributes(metric, "tenant")` says which attributes each metric keeps at a level of detail.

## Attributing your own spans

Your own tools run inside pydantic-ai's `execute_tool` span. To attribute a span you start yourself, use the same helper artifactr does:

```python
from opentelemetry import trace

from artifactr.telemetry import annotate, attribution

tracer = trace.get_tracer("my-app")


async def export_plan(workspace: Workspace, plan_id: str) -> None:
    with tracer.start_as_current_span("export plan"):
        annotate(
            attribution(
                tenant_id=workspace.tenant_id,
                workspace_id=workspace.workspace_id,
                actor=workspace.actor,
            )
        )
        ...
```

## Testing

Assert on telemetry with the SDK's in-memory exporter and reader, passing their providers explicitly so tests do not touch the global ones:

```python
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

spans = InMemorySpanExporter()
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
reader = InMemoryMetricReader()
meter_provider = MeterProvider(metric_readers=[reader])

workspaces = Workspaces(storage, tracer_provider=tracer_provider, meter_provider=meter_provider)
```
