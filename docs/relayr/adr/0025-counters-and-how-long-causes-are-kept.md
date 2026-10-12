# ADR-0025: Counters, and how long causes are kept

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:** [ADR-0021](0021-chains-continue-across-the-bridge.md): causes are forgotten after a time to live

## Context

[ADR-0015](0015-cursors-leases-and-dead-letters-in-the-ledger.md) logs a stopped follower and a dead letter, and promised them counters in phase 4. [ADR-0021](0021-chains-continue-across-the-bridge.md) records the run behind every write in `relayr_causes`, and left the table growing until phase 4 gave it a time to live. The libraries offer `configure_telemetry` contributions that keep their spans in Langfuse's traces and apply their metric cardinality policy ([artifactr ADR-0046](../../artifactr/adr/0046-telemetry-that-composes-across-libraries.md)).

## Decision

- **Two counters,** through the OpenTelemetry API: `relayr.followers.stopped`, with the tenant, workspace and `error.type`, and `relayr.dead_letters`, with the tenant, workspace and `relayr.event.type`. `Followers(meter_provider=...)` and `tracer_provider=` choose the providers; the global ones by default.
- **`relayr.otel.telemetry()` is relayr's contribution** to either library's `configure_telemetry`, behind the `otel` extra. Its span filter keeps the `relayr` scope's spans, and its views drop the workspace, or the tenant too, at the libraries' `MetricsDetail`.
- **Causes are kept a week by default.** `Followers(cause_ttl=...)` sets it. Each cause records when it was recorded (migration `0003`, with an index). A follower forgets its workspace's older causes as it takes the lease, and at most hourly while it holds it, through `Ledger.forget_causes(workspace, older_than=...)`, by the ledger's clock.
- **A write bridged after its cause is forgotten starts a chain of its own.** A week is far longer than any write waits to be bridged.

## Options considered

| Option | For | Against |
|---|---|---|
| **The follower forgets, as it holds the lease (chosen)** | No job to run; one process per workspace does it | Forgetting waits for a workspace to be followed |
| A scheduled job, such as a reflexr schedule | Runs whether or not a workspace is followed | One more thing to wire in every application |
| Causes kept for ever | Nothing to do | The table grows by a row or two per write |

## Consequences

- Easier: an operator sees stopped followers and dead letters in metrics, and the causes table stays bounded.
- Harder: a workspace no one follows keeps its causes until it is followed again.
