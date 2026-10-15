# ADR-0022: LiteLLM requests carry the propagated trace tags

**Status:** Accepted
**Date:** 2026-10-15
**Deciders:** Alex Nodeland
**Amends:** [relayr ADR-0024](../relayr/adr/0024-langfuse-sessions-tagged-with-each-other.md): its "LiteLLM's metadata doesn't carry the tags yet" ([lattice #86](https://github.com/alexnodeland/lattice/issues/86))

## Context

[relayr ADR-0024](../relayr/adr/0024-langfuse-sessions-tagged-with-each-other.md) tags a run that a thread event started with `thread:<id>`, and a turn relayr started with `rule:<name>` and `chain:<correlation id>`. It does so through the Langfuse attributes each library propagates around a turn or run. The libraries' `LiteLLMGateway` builds a request's tags from its own fixed fields and its static `tags=`, so those tags reached Langfuse's traces but not LiteLLM's spend and logs. [stackr RFC-0002](../stackr/rfcs/0002-the-combined-system.md) asks for the same tags in both.

Langfuse's `propagate_attributes(tags=...)` keeps the tags in OpenTelemetry's context, where the code running in the turn or run reads them. The Langfuse SDK has no public getter.

LiteLLM adds up each tag's spend per day, in a row for each tag and day ([ADR-0019](0019-a-tag-for-each-tenants-workspace.md)). A tag with an id for each thread or each chain adds rows without bound.

## Decision

- **A gateway adds the bounded trace tags Langfuse is propagating** to a request's tags: `lattice_core.litellm.add_propagated_tags(tags)` returns the request's own tags, then the propagated tags whose prefix is in `PROPAGATED_TAG_PREFIXES`, each once, in the order given and then held. The prefixes are `rule:` and `kind:`: as many as the application defines rules and artifact kinds. `tenant:` and `workspace:` are not among them, since a request carries them already.
- **`thread:` and `chain:` stay in Langfuse.** Each thread and each chain would add a row to LiteLLM's tag spend per day, without bound. A thread's or a chain's cost is read from Langfuse, by the session and the tag.
- **The function reads the context key Langfuse 4 keeps the tags under,** `langfuse.propagated.tags`, through OpenTelemetry's API: no Langfuse import, so the `litellm` extra needs only `opentelemetry-api` beside pydantic-ai.
- **artifactr's and reflexr's gateways both call it,** so they behave the same, and nothing changes for an application that sets no Langfuse tags. relayr changes nothing: its contexts already set them.
- **A turn's tags are set by its `TurnContext`.** artifactr's `Runner` runs each turn in a context of its own, so a tag propagated around `Runner.send` does not reach the turn; the `turn_context` argument does, as relayr's `bridged_turns` and `langfuse_turn` use it. reflexr's reactor runs a rule in the caller's context, and its `RunContext` sets them the same way.
- **The key is Langfuse's internal one, and the lockfile's version is the verified range.** It is built by `_get_propagated_context_key` in `langfuse/_client/propagation.py`, and lattice-core's `langfuse` extra, `langfuse>=4.15,<5`, locks to 4.16.0, which the tests ran against. The libraries' gateway tests set tags with `propagate_attributes` and read them in the request, so a release that renames the key fails them. There is no runtime check.

## Options considered

| Option | For | Against |
|---|---|---|
| **Read the propagated tags from the context, those with a bounded prefix (chosen)** | Automatic, for relayr and for any application's own contexts; no change for relayr; one function in lattice-core | Depends on Langfuse 4's context key, which its SDK doesn't document |
| The same, with every propagated tag | Simplest | `thread:` and `chain:` rows grow without bound in LiteLLM's tag spend |
| A callable on the gateway, returning extra tags for the current turn or run | No coupling to Langfuse | Each application wires it, and repeats what it already propagates for Langfuse |
| The libraries record the tags they propagate themselves | No coupling to Langfuse's key | relayr sets its tags around the libraries' contexts, not through them, so relayr would change too |

## Consequences

- Easier: a rule's cost, and an artifact kind's, are LiteLLM's spend by tag as well as Langfuse's traces, with no wiring.
- Harder: a thread's or a chain's cost is read from Langfuse only, not from LiteLLM's spend.
- Harder: `rule:` and `kind:` tags carry their names as they are, unlike ADR-0019's encoded tag: a name with a comma splits in a tag query. `tenant:` and `workspace:` already behaved so.
- Harder: a request lists a `rule:` tag once only when the two spellings are the same. reflexr's own `rule:<name>` and the one its Langfuse attributes propagate differ for a rule name with non-ASCII characters or over 200 characters, which the Langfuse tag limits (`_limit` turns the characters into `?` and truncates), so both appear.
- Revisit: when Langfuse offers a getter for the propagated tags, read it there.
