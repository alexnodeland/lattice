# Tracing across the bridge

This guide connects relayr's telemetry to an application's, so that a story that crosses the bridge can be followed in Tempo and Langfuse, and so that relayr's counters reach its metrics. The [architecture](../architecture.md#telemetry) says what relayr records.

## Configure

relayr records through the OpenTelemetry API, as the libraries do. Pass its contribution to the libraries' `configure_telemetry`, with the `otel` extra installed:

```python
import relayr.otel
import reflexr.otel
from artifactr.otel import configure_telemetry

telemetry = configure_telemetry(
    reflexr.otel.telemetry(),
    relayr.otel.telemetry(),
    service_name="app",
    langfuse="traces",
)
```

Its span filter keeps relayr's `relayr.bridge` spans in Langfuse's traces. Its views drop the tenant and workspace from relayr's counters at the `metrics_detail` you choose, as the libraries' do.

## Traces

Each library keeps its own traces, linked to each other:

- **A bridged event** is published in a `relayr.bridge <type>` span, linked to the span that committed the artifactr envelope. The run its event fires links to that span, so Tempo goes from a run back to the turn or request behind its event.
- **A turn a rule's run starts** with `send` links to the run's span.

## Langfuse

Give relayr's contexts to the libraries in place of their own, with the `langfuse` extra installed:

```python
from relayr.langfuse import bridged_run, bridged_turns

reactor = Reactor(automation, actions=actions, deps=outbound, run_context=bridged_run)
runner = Runner(agent, app=app, turn_context=bridged_turns(ledger))
```

- **A run whose rule fired on bridged events** is tagged `thread:<id>` for each of their threads, and its user is the person who acted in artifactr.
- **A turn that acts for a rule** is tagged `rule:<name>`, and `chain:<correlation id>` for the run that sent its message.

The sessions stay apart: a thread is artifactr's session, and a causal chain is reflexr's. The tags find one from the other.

## Metrics

| Counter | Counts | Attributes |
|---|---|---|
| `relayr.followers.stopped` | Followers that stopped on an error, until their workspace is opened again | tenant, workspace, `error.type` |
| `relayr.dead_letters` | artifactr envelopes a follower dead-lettered | tenant, workspace, `relayr.event.type` |

Both should be zero. Alert on either: a stopped follower bridges nothing until its workspace is opened again, and a dead letter is an event no rule saw.

## Causes

The ledger keeps the run behind each of the outbound adapter's writes for a week, by default. Each follower forgets older ones at most hourly while it holds its lease, once it has caught up with the log; a failure to forget is logged and changes nothing else. `Followers(cause_ttl=...)` sets how long; a write bridged after its cause is forgotten starts a chain of its own.
