# Observability

artifactr traces every turn, command, agent run and tool call, and counts what happens in each workspace, through the OpenTelemetry API ([ADR-0027](../adr/0027-opentelemetry-observability-with-langfuse.md)). It never configures OpenTelemetry itself: until your application sets up the SDK, recording costs nothing and goes nowhere. This page shows what is recorded and how to turn it on.

## Turning it on

The `otel` extra sets up the OpenTelemetry SDK in one call. Call it once, as early as the application starts:

```python
from artifactr.otel import configure_telemetry

telemetry = configure_telemetry(
    service_name="docplan",
    service_version="1.4.0",
    environment="production",
    otlp_endpoint="http://otel-collector:4318",  # or set OTEL_EXPORTER_OTLP_ENDPOINT
)

engine = create_async_engine("postgresql+asyncpg://db/app")
telemetry.instrument_engine(engine)

agent = Agent(
    "anthropic:claude-sonnet-5-5",
    deps_type=Session[AppDeps],
    capabilities=[ArtifactWorkspace(types=[Doc, Plan]), telemetry.capability()],
)
app = FastAPI(lifespan=lifespan)
telemetry.instrument_app(app)
```

It sets up:

- tracer, meter and logger providers, with `service.name`, `service.version` and `deployment.environment.name` on their resource, made global unless `set_global=False`
- OTLP over HTTP for traces, metrics and logs, to `otlp_endpoint` or wherever the `OTEL_EXPORTER_OTLP_*` environment variables point (`otlp_headers` adds credentials)
- the open instrumentations artifactr advises, FastAPI, SQLAlchemy, httpx and httpx2 (pydantic-ai's model providers use httpx2), for whichever of them is installed, using the stable HTTP semantic conventions; `instrument=` names others, such as `asyncpg` for an application that queries with asyncpg directly (SQLAlchemy's spans already cover the queries artifactr makes through it)
- views that apply artifactr's metric cardinality policy (see [Metrics](#metrics))
- a baggage span processor that copies a turn's `session.id` onto every span in it
- pydantic-ai's instrumentation settings: `telemetry.capability()` is its `Instrumentation` capability for your agents, with prompts and completions left out unless `include_content=True`

Instrumentation patches libraries, which only reaches objects created afterwards through the patched names. Most applications import `FastAPI` and `create_async_engine` before they configure telemetry, so pass the application to `telemetry.instrument_app(app)` and each engine to `telemetry.instrument_engine(engine)` (or `engines=` when configuring). The SQLAlchemy instrumentation declares support for versions below 2.1; it works with 2.1, which artifactr requires, so its version check is skipped.

Shut it down when the application stops, so buffered telemetry is flushed. `telemetry.shutdown()` does it, or use it as a context manager:

```python
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    with telemetry:
        yield
```

### With reflexr, or other libraries

An application that uses reflexr too configures telemetry once, with reflexr's contribution ([ADR-0046](../adr/0046-telemetry-that-composes-across-libraries.md)):

```python
import reflexr.otel
from artifactr.otel import configure_telemetry

telemetry = configure_telemetry(reflexr.otel.telemetry(), service_name="app")
```

`artifactr.otel.telemetry()` is artifactr's contribution, and `configure_telemetry` always adds it. Each contribution brings its library's metric views, a span filter for its traces, and the instrumentations it advises. `configure_telemetry` installs every library's views, instruments what any of them advises, and, with Langfuse, keeps a span that any of them keeps. reflexr's `configure_telemetry` takes artifactr's contribution the same way, so either library's will do. An application can contribute its own metric views too, with a `Contribution`.

### Configuring the SDK yourself

`configure_telemetry` is a convenience; artifactr only ever records through the OpenTelemetry API, so any SDK configuration works. `Workspaces`, `Runner` and `artifactr_router` use the global providers, or the ones you pass as `tracer_provider=` and `meter_provider=`. Add pydantic-ai's capability yourself, `Instrumentation(settings=InstrumentationSettings(tracer_provider=..., meter_provider=...))`, and every library's `metric_views(detail)` to your `MeterProvider` to limit metric detail. Keep a parent-based sampler, the SDK's default, so that polling stays untraced (see [Polling](#polling)). Never call `Agent.instrument_all()` from a library; it instruments every agent in the process.

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

Each envelope records the W3C trace context of the span that committed it, as `traceparent`: a command's `artifactr.commit` span, or the current span for a fact the agent records. reflexr's envelopes carry the same field, so code that follows the log, such as a bridge into reflexr, can link its spans to the request or turn that wrote an event. `current_traceparent()` returns the current span's context.

### Polling

Subscriptions and the feedback mirror poll storage: SQL storage reads the log every `poll_interval` for other processes' commits. They poll untraced, inside `artifactr.telemetry.untraced()`, which makes every span started in it a child of a span that is never sampled. So the database instrumentation records no span for a poll, and an idle application exports none; the instrumentations' metrics, such as the connection pool's, are still recorded. What a poll finds is traced where it happens: a commit in its request's trace, a turn in its own. Don't commit or publish inside `untraced()` yourself: its trace ids belong to the unsampled parent, so a revision or envelope would point at a trace that was never recorded. A sampler that ignores the parent, such as `always_on` or `traceidratio`, would trace each poll again.

## Metrics

artifactr's metrics are declared in a registry, `artifactr.telemetry.METRICS`, with the attributes each may carry. The [architecture](../architecture.md#metrics) lists them: commands and commit latency, turns and turn latency, runs by status, tool calls by tool and status, tokens, messages, artifact changes, proposals, and WebSocket connections.

Thread, run, artifact and message ids are never metric attributes; they are in the traces. Tenant and workspace are attributes by default, which suits most deployments. With many workspaces, keep less detail ([ADR-0036](../adr/0036-metric-cardinality-through-sdk-views.md)):

```python
telemetry = configure_telemetry(service_name="docplan", metrics_detail="tenant")  # or "none"
```

`metrics_detail` becomes OpenTelemetry views that drop the workspace (or the tenant too) before aggregation. Configuring the SDK yourself, pass `metric_views("tenant")` to the `MeterProvider`.

pydantic-ai records `gen_ai.client.token.usage` and `operation.cost` per model request, by model. artifactr's `artifactr.tokens` counts the same tokens by tenant and workspace, from each run's recorded usage.

### Dashboards

Seven Grafana dashboards ship in [`deploy/grafana/dashboards/`](https://github.com/alexnodeland/lattice/tree/main/packages/artifactr/deploy/grafana/dashboards): an overview of every tenant, one tenant, one workspace, the agent and its models, collaboration, the surfaces, and storage. They expect Prometheus with the data source uid `prometheus`, fed over OTLP (Prometheus's own OTLP receiver, or a Collector), which names the series as the registry predicts: `artifactr.commands` becomes `artifactr_commands_total`, `artifactr.commit.duration` becomes `artifactr_commit_duration_seconds`. [stackr](../../stackr/index.md) provisions them from its checkout of lattice, so its Grafana has the dashboards of the same commit; elsewhere, import the JSON files. Latency panels show exemplars, which link to the trace of a slow turn or commit.

Two of their settings follow from how metrics reach Prometheus:

- **Every query has a one-minute min step.** The OpenTelemetry SDK exports metrics once a minute by default, so Grafana's `$__rate_interval` must span several exports; with the min step it is at least four minutes. Shorter windows hold one sample at most, and rate panels show "No data". If your application exports less often, raise the queries' min step.
- **The Service variable's "All" is every service that records artifactr's metrics**, not every job in Prometheus. The names of pydantic-ai's metrics and of the HTTP and database pool metrics are shared with other services, such as stackr's LiteLLM proxy, which records `gen_ai.client.token.usage` too; "All" leaves theirs out.

## The session on every span

During a turn, the thread id is in OpenTelemetry baggage as `session.id`. `configure_telemetry` adds a `BaggageSpanProcessor` that copies it onto every span started in the turn, so the database and HTTP spans of a turn carry the session too, not only artifactr's and pydantic-ai's. Baggage also travels on outgoing HTTP requests (to model providers, for example), so it holds only the thread id: no tenant, user or content.

## Logs

`configure_telemetry` exports the standard `logging` module's records through OTLP, with the trace and span they were logged in; pass `logs=False` to leave logging alone.

## Langfuse

Langfuse is the primary backend for artifactr's traces and feedback ([ADR-0039](../adr/0039-the-langfuse-adapter.md)). With the `langfuse` extra, add it beside the Collector and give the `Runner` Langfuse's turn context:

```python
from artifactr.langfuse import langfuse_turn
from artifactr.otel import configure_telemetry

telemetry = configure_telemetry(service_name="docplan", langfuse="traces")  # keys: LANGFUSE_*
runner = Runner(agent, app=deps, turn_context=langfuse_turn)
```

- **Whole traces.** Langfuse's default keeps only LLM spans. With `langfuse="traces"`, Langfuse also keeps every span a library's contribution keeps: for artifactr, the scopes in `artifactr.telemetry.TRACE_SCOPES`, which are artifactr's, pydantic-graph's, the MCP SDK's and the FastAPI, SQLAlchemy, asyncpg and httpx instrumentations'. So a turn in Langfuse shows its commits, queries and HTTP calls around the model calls. `langfuse_client(...)` installs the same filter for artifactr alone, `should_export_span`.
- **Sessions and users.** `langfuse_turn` propagates each turn's attributes to every span in it: the thread as the session, the person who sent the message as the user, the trace name `turn`, tags for the tenant, the workspace and the kinds of artifact the thread follows (`tenant:acme`, `workspace:launch`, `kind:plan`), and artifactr's ids as metadata. Values are made ASCII and cut to 200 characters, as Langfuse requires. They stay in the process; nothing is sent as baggage.
- **Feedback as scores.** See [Evaluation](evaluation.md#scores-in-langfuse).

Configuring the SDK yourself, create the client with `langfuse_client(tracer_provider=...)`: it adds Langfuse's span processor, with the filter, to your provider.

### Through a Collector

A Collector can send the same traces to Langfuse over plain OTLP instead, as stackr's does. Then send Langfuse no spans of your own, or each would arrive twice, with `langfuse="scores"`: the client still sets each turn's session, user and tags on its spans, which reach Langfuse through the Collector, and records scores. Configuring the SDK yourself, pass `langfuse_client(tracer_provider=..., should_export_span=no_spans)`. Langfuse accepts OTLP over HTTP only, and needs its ingestion version header:

```yaml
exporters:
  otlphttp/langfuse:
    endpoint: https://langfuse.example.com/api/public/otel
    headers:
      Authorization: Basic ${env:LANGFUSE_AUTH}  # base64 of public_key:secret_key
      x-langfuse-ingestion-version: "4"
```

A Collector sends every span, so filter it there, or send Langfuse only the traces that contain LLM spans.

### Logfire

Logfire works as a second backend. Configure it first: it sets the global providers, which artifactr, pydantic-ai and Langfuse then use. Its scrubber redacts attributes whose names look sensitive, `session.id` among them, so keep the session and user:

```python
import logfire

from artifactr.langfuse import langfuse_client

KEPT = {("attributes", "session.id"), ("attributes", "user.id")}


def keep_session_and_user(match: logfire.ScrubMatch) -> object:
    return match.value if tuple(match.path) in KEPT else None


logfire.configure(scrubbing=logfire.ScrubbingOptions(callback=keep_session_and_user))
langfuse = langfuse_client()  # adds Langfuse to the global tracer provider
```

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
