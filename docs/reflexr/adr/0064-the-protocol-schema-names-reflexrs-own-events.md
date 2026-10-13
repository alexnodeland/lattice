# ADR-0064: The protocol schema names reflexr's own events

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:** [portalr ADR-0010](../../portalr/adr/0010-the-client-generated-types-and-resumable-stores.md): reflexr's events are no longer open in the client

## Context

An envelope's `event` is validated through the event registry, by its `type`, since the application's events share the log with reflexr's own. So the protocol schema, and the OpenAPI document, typed it as open: `{type, ...}`. reflexr's own events, `reflexr:rule_installed`, `reflexr:run_started` and the rest, had documented fields but no schema. A client read them by name: portalr's reducer did, and nothing checked it against reflexr's events ([lattice #83](https://github.com/alexnodeland/lattice/issues/83)). artifactr's schema names every event it defines, with an open fallback, `UnknownEvent`.

## Decision

- **An event's JSON Schema is `LoggedEvent`:** one of reflexr's own events, each with its fields and its `type` as a constant, or `OtherEvent`, an object with a qualified `type` that is none of reflexr's, and any other fields. That holds in the protocol schema, and in the OpenAPI document as validated and as serialized.
- **reflexr's own events are open on the wire.** Their variants allow fields they don't name, since the protocol's changes within v1 are additive, and a newer version's optional field must still match, as artifactr's events do.
- **Only the wire names `type`.** An event type's own model, and its own JSON Schema, which an agent's tools show it, keep only its fields, and reject any other.
- **Validation doesn't change.** Events are still validated through the registry, by their `type`. `LoggedEvent` and `OtherEvent` describe the wire, are private to `reflexr.core.events`, and nothing validates against them; a test checks real envelopes, one of each of reflexr's events, an application's and an unknown one, against the schema.
- **portalr's client generates the types,** and its reflexr reducer and its stale queries are typed and exhaustive over reflexr's events, as its artifactr ones are. The application's events change nothing there.

## Options considered

| Option | For | Against |
|---|---|---|
| **The schema names reflexr's events, with an open fallback (chosen)** | Clients type them, and a new event of reflexr's is a compile error until they handle it | The wire's schema and a model's own differ, in `type` and in extra fields |
| A schema of reflexr's events apart from the protocol | The protocol unchanged | Clients join the two by hand |
| Keep them open | Nothing to change | Clients read fields by name, unchecked |

## Consequences

- Easier: a client knows each of reflexr's events' fields, and portalr's reducer is checked against them.
- Harder: an event of reflexr's added later is in the schema, so a client that switches over them handles it before it compiles.
