# ADR-0023: Traces linked across the bridge

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[ADR-0004](0004-sessions-linked-not-continued.md) keeps a turn and a run as separate traces, linked rather than continued. artifactr records on each envelope the `traceparent` of the span that committed it, and a turn links to the span that sent its message ([artifactr ADR-0035](../../artifactr/adr/0035-a-turn-is-its-own-trace.md)). reflexr's runs link to the envelopes that made their rule fire, by those envelopes' `traceparent`. The follower publishes from a task with no span, so a bridged event's `traceparent` named nothing, and a run could not be traced back to the turn behind its event. The libraries record through the OpenTelemetry API only, and relayr does the same ([artifactr ADR-0046](../../artifactr/adr/0046-telemetry-that-composes-across-libraries.md)).

## Decision

- **The follower publishes each bridged event in a span of its own,** `relayr.bridge <type>`, a consumer span at the root of a new trace, linked to the span that committed the artifactr envelope. reflexr's publish span is its child, and the run links to that. So in Tempo, a run links to the bridge, and the bridge to the turn or request behind the event.
- **A run's message starts a turn linked to the run's span:** `RunActions.send` calls artifactr's `Runner.send` inside the run's span, and the turn links to it.
- **A turn starts from an empty context:** artifactr's `Runner` attaches an empty context before it starts a turn's span ([artifactr ADR-0059](../../artifactr/adr/0059-a-turn-starts-from-an-empty-context.md)), so a run's Langfuse attributes and baggage stay with the run.
- **So does a follower.** It is started by whatever opens its workspace first, such as a request, and attaches an empty context as it starts, so its bridge spans are never children of that request, and carry none of its attributes.
- **Attributes are relayr's own,** named as the libraries name theirs: `relayr.tenant.id`, `relayr.workspace.id`, `relayr.event.type` and `relayr.envelope.seq`, under the instrumentation scope `relayr`.

## Options considered

| Option | For | Against |
|---|---|---|
| **A bridge span linked to the envelope's span (chosen)** | Each side keeps its own trace (D4), and Tempo follows the links both ways | One more span per bridged event |
| Publish in the envelope's trace, as a child of its span | No extra span | Continues the turn's trace into reflexr, against D4, sometimes long after the turn ended |
| No span, and no link | Nothing to record | A run can't be traced to what caused its event |

## Consequences

- Easier: from a run, Tempo reaches the turn behind its event; from a turn a rule started, the run.
- Harder: with sampling, a bridge span may be kept while the span it links to was dropped, or the reverse; links are best effort.
