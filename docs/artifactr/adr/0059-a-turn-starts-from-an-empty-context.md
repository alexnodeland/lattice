# ADR-0059: A turn starts from an empty context

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:** [ADR-0035](0035-a-turn-is-its-own-trace.md): a turn carries nothing its caller propagated

## Context

[ADR-0035](0035-a-turn-is-its-own-trace.md) makes a turn its own trace, linked to the span that started it. The `Runner` started the turn's span with no parent, but attached the turn's context on top of its caller's. Everything the caller had propagated reached every span of the turn: its baggage, and Langfuse's propagated attributes. A request's tags, or the tags of a reflexr run that sent the message through relayr, were then filed under the turn's session, against [relayr ADR-0004](../../relayr/adr/0004-sessions-linked-not-continued.md).

## Decision

- **A turn attaches an empty context before it starts its span,** and detaches it when the turn ends. The link to the caller's span stays: the caller is read before.
- **Attributes for a turn go in its `turn_context`,** such as `langfuse_turn` or relayr's `bridged_turns`. Nothing propagated around `Runner.send` or a request reaches the turn.

## Options considered

| Option | For | Against |
|---|---|---|
| **An empty context (chosen)** | A turn's trace and session carry only the turn's own attributes, wherever it was started | A request's own attributes, such as an application's tag, no longer reach its turns; they belong in `turn_context` |
| The caller's context, as before | Request-level attributes reach the turn | Another session's tags and baggage leak into the turn |

## Consequences

- Easier: a turn is the same trace, with the same attributes, whether a request, a WebSocket, MCP or another library started it.
- Harder: an application that relied on attributes propagated around a request to tag its turns moves them into `turn_context`.
