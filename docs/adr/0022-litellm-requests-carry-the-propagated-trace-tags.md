# ADR-0022: LiteLLM requests carry the propagated trace tags

**Status:** Accepted
**Date:** 2026-10-15
**Deciders:** Alex Nodeland
**Amends:** [relayr ADR-0024](../relayr/adr/0024-langfuse-sessions-tagged-with-each-other.md): its "LiteLLM's metadata doesn't carry the tags yet" ([lattice #86](https://github.com/alexnodeland/lattice/issues/86))

## Context

[relayr ADR-0024](../relayr/adr/0024-langfuse-sessions-tagged-with-each-other.md) tags a run that a thread event started with `thread:<id>`, and a turn relayr started with `rule:<name>` and `chain:<correlation id>`. It does so through the Langfuse attributes each library propagates around a turn or run. The libraries' `LiteLLMGateway` builds a request's tags from its own fixed fields and its static `tags=`, so those tags reached Langfuse's traces but not LiteLLM's spend and logs. [stackr RFC-0002](../stackr/rfcs/0002-the-combined-system.md) asks for the same tags in both.

Langfuse's `propagate_attributes(tags=...)` keeps the tags in OpenTelemetry's context, where the code running in the turn or run reads them. The Langfuse SDK has no public getter.

## Decision

- **A gateway adds the trace tags Langfuse is propagating in the current context** to a request's tags: `lattice_core.litellm.add_propagated_tags(tags)` returns the request's own tags, then the propagated ones, each once, in the order given and then held. It reads the context key Langfuse 4 keeps them under, `langfuse.propagated.tags`, through OpenTelemetry's API: no Langfuse import, so the `litellm` extra needs only `opentelemetry-api` beside pydantic-ai.
- **artifactr's and reflexr's gateways both call it,** so they behave the same, and nothing changes for an application that sets no Langfuse tags. relayr changes nothing: its contexts already set them.
- **A turn's tags are set by its `TurnContext`.** artifactr's `Runner` runs each turn in a context of its own, so a tag propagated around `Runner.send` does not reach the turn; the `turn_context` argument does, as relayr's `bridged_turns` and `langfuse_turn` use it. reflexr's `RunContext` is the same.
- **The key is Langfuse's internal one,** so the libraries' gateway tests set tags with `propagate_attributes` and read them in the request. A Langfuse release that renames the key fails them, where the dependency range (`langfuse<5`) lets it in.

## Options considered

| Option | For | Against |
|---|---|---|
| **Read the propagated tags from the context (chosen)** | Automatic, for relayr and for any application's own contexts; no change for relayr; one function in lattice-core | Depends on Langfuse 4's context key, which its SDK doesn't document |
| A callable on the gateway, returning extra tags for the current turn or run | No coupling to Langfuse | Each application wires it, relayr included, and repeats what it already propagates for Langfuse |
| The libraries keep their own record of the tags they propagate | No coupling to Langfuse's key | relayr's tags are set around the libraries' contexts, not through them, so relayr would need to change as well |

## Consequences

- Easier: a chain's or a rule's cost is its LiteLLM spend by tag as well as its Langfuse traces, with no wiring.
- Harder: every tag Langfuse is propagating reaches LiteLLM, not relayr's alone. artifactr's turn tags `kind:<artifact kind>` now also appear on its requests; `tenant:` and `workspace:` do not repeat. Each tag is a row in LiteLLM's tag spend per day.
- Harder: `thread:`, `chain:` and `rule:` tags, like `tenant:` and `workspace:`, carry their ids as they are, unlike [ADR-0019](0019-a-tag-for-each-tenants-workspace.md)'s tag; an id with a comma splits in a tag query.
- Revisit: when Langfuse offers a getter for the propagated tags, read it there.
