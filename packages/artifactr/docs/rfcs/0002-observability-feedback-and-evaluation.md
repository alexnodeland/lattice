# RFC-0002: Observability, feedback, evaluation and the LLM gateway

**Status:** Accepted
**Author:** Alex Nodeland
**Created:** 2026-09-28
**Discussion:** accepted on 2026-09-28
**Siblings:**
- [reflexr RFC-0002](https://github.com/alexnodeland/reflexr/blob/main/docs/rfcs/0002-observability-feedback-and-evaluation.md) makes the same changes in reflexr.
- [evalr RFC-0001](https://github.com/alexnodeland/evalr/blob/main/docs/rfcs/0001-v0.1-implementation-plan.md) builds the shared eval kit.
- [stackr RFC-0001](https://github.com/alexnodeland/stackr/blob/main/docs/rfcs/0001-v0.1-implementation-plan.md) builds the infrastructure template these run on.

## Summary

Make artifactr deeply observable and evaluable:

- **Tracing:** every turn, command, agent run and tool call is an OpenTelemetry span with GenAI attributes, attributed to its tenant, workspace, thread and actor, with the thread as the session.
- **Metrics and dashboards:** OpenTelemetry metrics from a registry, with Grafana dashboards shipped in the repository.
- **Feedback:** typed and scoped to artifacts, threads, turns and messages, recorded in the log and mirrored to Langfuse scores.
- **Evaluation:** an `[evals]` extra that connects artifactr to **evalr**, the shared eval kit. evalr covers DSPy judges optimized with GEPA, TypeSafe Jev evaluators, and end-to-end measures (task completion, drop-off, rewrite rate).
- **LLM gateway:** a `[litellm]` extra that routes agents through a LiteLLM proxy (model groups, fallbacks, budgets, guardrails), attaching tenant, session and trace metadata to every request.
- **Dev environment:** a small contributor Docker Compose file and a Compose-based dev container. The full infrastructure (local Supabase, LiteLLM, the OpenTelemetry Collector, Grafana with Prometheus, Tempo, Loki and Pyroscope, and self-hosted Langfuse) lives in **stackr**, the infrastructure template, which provisions artifactr's dashboards.

The libraries depend on the OpenTelemetry **API** only. The application configures the SDK, and a helper makes that one call.

## Motivation

The library can't be improved without seeing what its agents do and whether people are satisfied with it. The things to see:

- which runs are slow or costly
- which tool calls fail
- how often people rewrite what the agent wrote
- whether a thread ended with the task done

Today artifactr has no traces or metrics of its own; pydantic-ai's instrumentation can be turned on, but nothing ties its spans to threads, tenants or artifacts. Feedback has no home. Evaluations would need bespoke glue in every application.

The same capabilities are planned for reflexr, and the combined system will need them to agree, so the conventions are designed once for both.

## Design

### Tracing

- **API only.** artifactr uses `opentelemetry-api` (made an explicit dependency), with tracer and meter scope `artifactr` at the package version. `Workspaces`, `Runner` and the surfaces accept an optional `tracer_provider` and `meter_provider`, defaulting to the global ones. The library never configures the SDK, never calls `Agent.instrument_all()`, and never creates a Langfuse client.
- **Spans** follow the OpenTelemetry GenAI conventions where they apply:

| Span | Name | Key attributes |
|---|---|---|
| A turn: the `Runner` handling a message, or an answer that resumes a run | `invoke_workflow turn` | `gen_ai.operation.name=invoke_workflow`, `gen_ai.workflow.name=turn` |
| A command committed through `Workspace.commit` | `artifactr.commit {type}` | `artifactr.command.type`, `artifactr.outcome` |
| The agent run inside a turn (pydantic-ai's `invoke_agent`) | pydantic-ai's | artifactr's attributes are added by the capability's `wrap_run` |
| A tool call (pydantic-ai's `execute_tool`) | pydantic-ai's | `artifactr.artifact.id`, plus the patch summary for artifact tools |
| A WebSocket session and REST request | `artifactr.stream`, FastAPI's own | `artifactr.workspace.id` |

- **Attribution on every span artifactr owns or wraps:**
  - `session.id` and `gen_ai.conversation.id` set to the thread id: the session
  - `user.id` set to the person's actor id
  - `artifactr.tenant.id`, `artifactr.workspace.id`, `artifactr.thread.id`, `artifactr.run.id` and `artifactr.actor.kind`
  - `langfuse.observation.type`, where it helps the Langfuse UI
- **pydantic-ai runs.** The Runner passes `conversation_id=thread_id` to every agent run. artifactr's run id is **not** passed as pydantic-ai's `run_id`, because an artifactr run spans pauses and each resume is a new pydantic-ai run. It is an attribute instead.
- **Trace links.** A `Run` records the OpenTelemetry trace id of each attempt (`trace_ids`), stored with the run, so feedback on a turn or artifact can be attached to the right trace. SQL storage adds a migration.
- **Content capture** (prompts, messages, artifact bodies on spans) follows pydantic-ai's `include_content`, and is off in artifactr's own spans unless enabled.
- **End to end.** Application-level spans (FastAPI, SQLAlchemy, asyncpg, httpx, and `httpx2`, which pydantic-ai's providers use) come from the open OpenTelemetry instrumentations, set up by the telemetry helper. The thread id is also placed in OpenTelemetry baggage during a turn, so database and HTTP spans can carry the session through `BaggageSpanProcessor`. That recipe is a spike (below).

### Metrics and dashboards

- **A metric registry** (`artifactr.telemetry.metrics`) declares every metric: name, instrument, unit, description and allowed attributes. Examples:
  - `artifactr.commands` (counter by command type and outcome) and `artifactr.commit.duration` (histogram)
  - `artifactr.turns` and `artifactr.turn.duration`
  - `artifactr.runs` (by status)
  - `artifactr.proposals` (created, accepted, rejected)
  - `artifactr.feedback` (by type)
  - `artifactr.stream.connections` (up-down counter) and `artifactr.stream.disconnects` (by close code)

  pydantic-ai adds `gen_ai.client.token.usage` and `operation.cost`. Tempo's metrics generator adds span metrics and service graphs.
- **Cardinality policy.** Thread, turn, run, artifact and message ids are **never** metric attributes; those granularities come from traces, linked through exemplars. Tenant and workspace are attributes by default, and `metrics_detail="workspace" | "tenant" | "none"` limits them for large deployments.
- **Dashboards** live in `deploy/grafana/dashboards/`, provisioned in Compose:
  - Overview: all tenants
  - Tenant
  - Workspace
  - Agent and LLM: usage, cost, latency, tool failures
  - Collaboration: proposals, rewrite rate, feedback
  - Surfaces: HTTP, WebSocket, MCP
  - Storage

  A test checks that every query in the dashboards refers to a metric in the registry, so the dashboards cannot drift from the code.

### Typed feedback

- **`Feedback`** is a Pydantic base class. Subclasses register by name, like artifact types, and declare the targets they apply to:

```python
class Helpfulness(Feedback, name="helpfulness", targets={"turn", "thread"}):
    rating: Annotated[int, Field(ge=1, le=5)]
    reason: str | None = None
```

- **Targets:**
  - `ArtifactTarget(artifact_id, version)`
  - `ThreadTarget(thread_id)`
  - `TurnTarget(run_id)`
  - `MessageTarget(message_id)`
- **Recording:** a new command, `give_feedback`, is recorded through the one write path as a `feedback_given` event. Core validates the type and the target. REST, WebSocket and MCP get it for free ([ADR-0022](../adr/0022-surfaces-over-one-command-handler.md)).
- **Evaluators give feedback too.** An evaluator's verdict *is* a feedback instance, given by a new actor kind, `EvaluatorActor(name, version)`. Human and evaluator feedback share types, so their agreement is a query rather than a migration.
- **Score mapping:** each field becomes a Langfuse score named `{type}.{field}`: bounded numbers are NUMERIC, bools BOOLEAN, `Literal` and `Enum` CATEGORICAL, strings TEXT. Score configs are generated from the types.

### Langfuse (the `[langfuse]` extra)

Langfuse is the primary observability backend, open source and self-hostable. The extra adds:

- **A span filter** for `Langfuse(should_export_span=...)`. By default Langfuse keeps only LLM spans. The filter keeps those plus artifactr's, pydantic-graph's and the database, HTTP and FastAPI instrumentations', so traces stay whole.
- **A context helper** over `langfuse.propagate_attributes`, which sets session, user, tags (tenant, workspace, the kinds of artifact in focus) and trace name per turn, within Langfuse's limits.
- **A feedback mirror** that reads `feedback_given` from the log and writes idempotent scores to Langfuse. Turn and message feedback go to the turn's trace, thread feedback to the session, and artifact feedback to the trace of the run that wrote that version and to the session.
- **Score config sync** from the registered feedback types.
- **Collector guidance:** plain OTLP to Langfuse's HTTP endpoint, with the `x-langfuse-ingestion-version=4` header.

Logfire is supported as a secondary backend by a documented recipe: Logfire configures first, and its scrubber must allow `session.id` and `user.id`. It is never required.

### Telemetry helper (the `[otel]` extra)

`configure_telemetry(service_name=..., otlp_endpoint=..., langfuse=True, instrument=[...])` is for applications and the reference implementation. It sets up:

- the tracer, meter and logger providers, with resource attributes including `deployment.environment.name`
- OTLP export to the Collector
- the open instrumentations for FastAPI, SQLAlchemy, asyncpg, httpx and `httpx2`
- pydantic-ai's `Instrumentation` capability settings
- optionally, Langfuse with the recommended filter

It returns a handle that shuts everything down cleanly. No part of the library requires it.

### Evaluation (the `[evals]` extra)

evalr is the shared eval kit, specified in its own RFC. artifactr's extra connects the two:

- **Datasets from the log:** feedback of a type, with its target's context (thread transcript, artifact versions, turn events), becomes evalr dataset items. evalr syncs them to Langfuse datasets and Hugging Face datasets.
- **Experiment tasks** replay a thread's turn against a new agent, prompt or model in an isolated workspace, so evalr can run Langfuse experiments.
- **Online evaluation:** `Runner(evaluators=[...])` runs evaluators after turns end. Their verdicts are recorded as feedback from an `EvaluatorActor`, with a sampling rate and a budget.
- **End-to-end measures** for chats with artifacts. Rewrite rate and drop-off are exact and cheap; task completion needs judgement:

| Measure | Definition | How |
|---|---|---|
| Rewrite rate | Share of agent-written revisions that a person substantially changes within a window | Deterministic, from revisions |
| Drop-off | Threads whose last agent turn is followed by no human activity within a window, or by an unresolved proposal | Deterministic, from the log |
| Task completion | Whether the thread achieved what the person asked, with quality | A DSPy judge or a Jev evaluator over the transcript and final artifacts, producing a `TaskCompletion` feedback type |

### LLM gateway (the `[litellm]` extra)

LiteLLM runs as a proxy in stackr and owns routing (model groups, fallbacks, load balancing), budgets, rate limits and guardrails. artifactr reaches it through pydantic-ai's native `LiteLLMProvider`, so the library needs no dependency on the litellm package. The extra provides:

- **`litellm_model(name, api_base=..., api_key=...)`**, a pydantic-ai model pointed at a proxy model group.
- **Per-request metadata**, added by the capability in `before_model_request` through `extra_body` and `extra_headers`:
  - the tenant, used to select the tenant's LiteLLM team key
  - workspace, thread and run as tags and metadata
  - the session id, plus the trace id so LiteLLM's own logs join the same Langfuse trace
- **Guardrails by policy:** a workspace (or a rule, in reflexr) names the guardrails its requests use. A request blocked by a guardrail becomes a typed, recorded outcome. The run fails with a `guardrail_blocked` reason, and the agent can be told why, instead of seeing an opaque HTTP error.
- **Tenancy:** each tenant is a LiteLLM team with its own virtual keys, budgets and rate limits. The extra resolves the key for the workspace's tenant through a callback the application supplies. Keys never appear in the log or on spans.

### Dev environment and the stack

- **Contributor Compose:** the repository's `compose.yaml` holds what developing artifactr needs: plain PostgreSQL by default (the tests need nothing more), and the reference app under an `app` profile. Applications use stackr's local Supabase instead, whose PostgreSQL the SQL storage uses unchanged.
- **The dev container** is built on that Compose file and sets the test environment. When stackr's stack is running, it joins stackr's network, and `OTEL_EXPORTER_OTLP_ENDPOINT` points at the stack's Collector.
- **Dashboards stay here,** next to the metric registry they are tested against. Each release publishes them as assets, and stackr provisions them by version.
- **CI** validates the Compose file and the dashboard JSON without starting containers.

### Shared conventions with reflexr

| Convention | artifactr | reflexr |
|---|---|---|
| Scope | `artifactr` | `reflexr` |
| Session (`session.id`, `gen_ai.conversation.id`) | Thread id | Correlation id (the causal chain) |
| Workflow span | `invoke_workflow turn` | `invoke_workflow {rule}` |
| Ids on spans | `artifactr.{tenant,workspace,thread,run,artifact}.id` | `reflexr.{tenant,workspace,run}.id`, `reflexr.rule`, `reflexr.event.type` |
| Trace links | `Run.trace_ids` | `Run.trace_ids` |
| Feedback event | `feedback_given` | `feedback_given` |
| Evaluator actor | `EvaluatorActor(name, version)` | The same |
| Score names | `{type}.{field}` | The same |
| Metric names | `artifactr.*`, with a registry and the cardinality policy | `reflexr.*`, the same |
| LiteLLM metadata | Tenant (team key), `artifactr` tags, session, trace id | Tenant (team key), `reflexr` tags, session, trace id |

## Drawbacks

- More dependencies at the edges: `opentelemetry-api` in core, and heavier extras.
- More repositories to keep in step: the libraries, evalr and stackr. The shared-conventions table and version-pinned dashboards keep them aligned.
- The GenAI conventions are still in development; attribute names may change, and a constants module keeps the change in one place.

## Alternatives

- **Langfuse's SDK in core:** simpler for Langfuse users, but it forces the OpenTelemetry SDK and a global provider on everyone.
- **Logfire as primary:** the best end-to-end experience, but a paid platform.
- **Feedback in Langfuse only:** no replay from the log, and datasets would depend on Langfuse.

## Unresolved questions

- **Baggage recipe:** whether `BaggageSpanProcessor` reliably carries the session onto database and HTTP spans in a real Langfuse deployment. A spike in phase A1.
- **Jev input budget:** Jev's state is limited to 32K tokens, so long threads need summarizing before evaluation (evalr's concern).
- **Rewrite threshold:** what counts as a "substantial" rewrite (a share of changed text, or a semantic judgement). The first version uses a text-diff share.

## Tracking

- [x] A1: telemetry core: spans, attribution, trace ids on runs, metric registry, `[otel]` helper (trace ids needed no migration: [ADR-0033](../adr/0033-trace-links-on-runs-and-revisions.md))
- [x] A2: typed feedback: `Feedback`, targets, `give_feedback`, `feedback_given`, `EvaluatorActor`, surfaces
- [ ] A3: `[langfuse]` extra: span filter, context helper, feedback mirror, score configs
- [ ] A4: dev environment: contributor Compose, dev container, Grafana dashboards with a dashboard-to-registry test, and dashboards published as release assets
- [ ] A7: `[litellm]` extra: `litellm_model`, per-request metadata, guardrail policies, typed guardrail outcomes, tenant key resolution
- [ ] A5: `[evals]` extra over evalr: datasets from the log, experiment tasks, online evaluators, end-to-end measures
- [ ] A6: docs: an observability guide, an evaluation guide, and the architecture updated
