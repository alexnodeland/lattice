# ADR-0006: Bridged types in the `artifactr` namespace

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Records decision D6 of [stackr RFC-0002][rfc-0002], the combined system.

## Context

reflexr's event registry is process-global. With flat names, its own facts (`run_started`, `feedback_given`) would have collided with artifactr's event names once bridged. The design's draft proposed a prefix now and a rename later; D6 chose to settle reflexr's namespacing first, so that rules, including rules drafted in chat, never name a type that is later renamed. [reflexr ADR-0039][r-adr-0039] settled it: every event type is `namespace:name`, and reflexr's own facts are `reflexr:*`.

## Decision

- **Bridged types are declared under a base with `event_namespace="artifactr"`**, so each is `artifactr:<type>`:
  - `artifactr:message_posted`
  - `artifactr:artifact_created`, `artifactr:artifact_changed` and `artifactr:artifact_archived`
  - `artifactr:proposal_created` and `artifactr:proposal_resolved`
  - `artifactr:turn_ended`, for artifactr's `run_ended`, so that "run" means one thing inside reflexr
  - `artifactr:feedback_given`
- **An application's projections** of its `app_event`s and artifact kinds publish its own types, in its own namespace.
- **Each bridged envelope's actor is `SourceActor("artifactr")`**, since relayr published it. The artifactr actor goes in an `author` field, so rules can filter on who acted.
- **Phase 1 waited for reflexr #45**, and starts now that reflexr #83 has implemented it.

## Options considered

| Option | For | Against |
|---|---|---|
| Prefix now (`artifactr.message_posted`), move to #45's namespaces later | Works at once, since the registry accepted dotted names | A rename when #45 lands. Rules from chat name these types, so the move needs a mapping |
| **Decide #45 first (chosen)** | Right the first time: no rename, and no mapping for rules that name the old types | Phase 1 waits for a wire-format decision in reflexr |

## Consequences

- Easier: a bridged type can never collide with reflexr's facts or an application's types, and its name is stable from the first release.
- Harder: in reflexr's registry, the `artifactr` namespace is relayr's, not artifactr's, and reflexr refuses any other base that declares it in the same process.

[r-adr-0039]: https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0039-namespaced-event-types.md
[rfc-0002]: https://github.com/alexnodeland/stackr/blob/main/docs/rfcs/0002-the-combined-system.md#d6-bridged-event-names-before-reflexr-45
