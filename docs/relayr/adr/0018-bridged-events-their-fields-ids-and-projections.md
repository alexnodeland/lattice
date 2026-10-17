# ADR-0018: Bridged events, their fields, ids and projections

**Status:** Accepted, and the amendment below
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[ADR-0006](0006-bridged-types-in-the-artifactr-namespace.md) names the bridged types, and [stackr RFC-0002][rfc-0002-inbound] lists what each carries, that an application's `app_event`s and artifact kinds are bridged by "a mapping function per type", and that "the bridged event id comes from the artifactr envelope id". It leaves open what every type has in common, how an id is derived when one envelope could become several events, and whether an application's mapping for an artifact kind adds to the default set's events or takes their place.

## Decision

- **Every bridged type carries where it came from:** `author`, the artifactr actor; `thread_id`; and `turn_id`, artifactr's run id. A run is reflexr's word, so artifactr's runs are turns, as `run_ended` is bridged as `artifactr:turn_ended`. `proposal_created` carries `proposed_by` as well as `author`, so a rule reads the proposer the same way on both proposal events.
- **The fields keep artifactr's types:** a patch is artifactr's `Patch`, a proposed change its `ProposedChange`, a feedback target its `FeedbackTarget`, and an author its `Actor`. Rules read them as JSON, such as `F.author.kind`.
- **An envelope becomes at most one event, whose id is the envelope's id**, unchanged.
- **`Projections` holds the application's mappings:** one per `app_event` name, and one per artifact kind, which takes the place of the default set's `artifact_created`, `artifact_changed` and `artifact_archived` for that kind. Proposals on the kind are bridged as the default set's. An `app_event` with no mapping stays in artifactr. A mapping returns its own event, in the application's namespace, or None.
- **`thread_created` isn't in the default set,** which RFC-0002 leaves as an open question.
- **`BRIDGED` lists the bridged types,** for reflexr's `Workspaces(events=...)`; a type it doesn't accept stops the follower ([ADR-0015](0015-cursors-leases-and-dead-letters-in-the-ledger.md)).

## Options considered

| Option | For | Against |
|---|---|---|
| **A kind's mapping replaces its artifact events (chosen)** | One event per envelope, so the id is the envelope's | A rule on `artifactr:artifact_changed` doesn't see that kind |
| A kind's mapping adds an event beside them | Both kinds of rule see it | Two events from one envelope need derived ids, and the bridged log doubles for that kind |
| **The envelope's id, unchanged (chosen)** | What RFC-0002 says; an operator finds one from the other | Ids are shared across the two logs, which use different random ids by default |
| An id derived from the envelope's | Room for several events per envelope | A mapping to explain, for nothing phase 1 needs |

## Consequences

- Easier: a bridged event names its artifactr envelope, and a rule can filter on who acted, in which thread and turn.
- Harder: a redelivered envelope whose projection now gives a different event publishes nothing: reflexr keeps the id's first event. A changed projection applies to envelopes it hasn't bridged yet.
- Harder: an application that wants both its typed event and the default set's for an artifact kind can't have both; its mapping's event has to carry what its rules need.

## Amendment (2026-10-17): answers, and a projection per deferred tool

[lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md) bridges answers to paused turns, and lets a form's answer and a form's submission reach a rule as one event.

- **`artifactr:deferred_answered` carries** `tool_call_id`, `tool_name`, `answer` and `approved`, beside `author`, who answered, and `thread_id`. Its `turn_id` is the turn that asked, from the event's `run_id`: the envelope names that run, but a person wrote it, not the turn. `tool_name` is None only for answers artifactr recorded before it named the tool. A chat message that answers is bridged as its `artifactr:message_posted` too.
- **`Projections` gains a third kind of mapping,** beside those per `app_event` name and per artifact kind: one per deferred tool's name, `Projections(deferred={"ask_form": ...})`, which takes the place of `artifactr:deferred_answered` for answers to that tool, as a kind's mapping takes the place of its artifact events. An answer whose tool has no mapping, or that names none, is bridged as the default set's. `relayr.ui`, the `forms` extra ([ADR-0033](0033-one-event-for-both-ways-of-asking.md)), uses it to bridge an `ask_form` answer and a form's submission both as `ui:form_submitted`.
- **An answer to a rule's paused turn joins the turn's chain without going deeper,** as a person's answer to a rule's proposal joins the proposal's ([ADR-0021](0021-chains-continue-across-the-bridge.md)): the follower finds the turn's cause in the ledger by the answer's run, and publishes with its correlation id and no causation. An answer to any other turn starts a chain of its own.

[rfc-0002-inbound]: ../../stackr/rfcs/0002-the-combined-system.md#inbound-artifactr-to-reflexr
