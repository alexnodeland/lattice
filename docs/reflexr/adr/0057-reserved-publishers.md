# ADR-0057: Reserved publishers

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Designs the values of [ADR-0039](0039-namespaced-event-types.md)'s decision 4, which put reserved publishers on `Workspaces`, keyed by namespace, with per-type exceptions.

## Context

`Workspaces(emitted=[...])` reserves types to runs, but nothing reserves a type to one publisher ([lattice #8](https://github.com/alexnodeland/lattice/issues/8), was reflexr #72). Any client allowed to publish could send an event that only a bridge or an integration should.

[stackr RFC-0002](../../stackr/rfcs/0002-the-combined-system.md) bridges artifactr's events into reflexr as `artifactr:*`, published as `SourceActor(name="artifactr")`, and rules act on them. One installs rules a person accepted in chat, so a forged `artifactr:proposal_resolved` must install nothing (phase 5). Until types can be reserved, those rules check the envelope's actor themselves.

ADR-0039 settled where the policy lives and its keys. It left three questions open: what a value names, whether `emitted=` folds into it, and where the check sits.

## Decision

- **`Workspaces(publishers={key: [actor, ...]})`.** A key is a namespace (`"artifactr"`) or a qualified type (`"plans:plan_approved"`). A type's entry replaces its namespace's, so an exception can widen or narrow it.
- **A value is actors, compared by `participant`.** `SourceActor(name="artifactr")` is the publisher `source:artifactr`. Every run of one rule's agent shares a participant (`agent:<rule>`), so a type can be reserved to a rule's runs. Full equality could never match one: each run has its own `run_id`.
- **Anyone else is `forbidden`, runs included:** `"artifactr:proposal_resolved events are reserved to source:artifactr"`. A rule's agent that emits a bridged type is as much a forgery as a client that publishes one.
- **A fixed check beneath `authorize`,** beside the refusal of `reflexr:*`. `publish` asks `authorize` for `reflexr:publish` first, then checks the type. The hook decides who may publish at all, and the policy decides who may publish a type. grantr can't grant around it. It adds nothing to `ACTIONS`.
- **Keys are checked at startup,** as `events=`, `emitted=` and rules are. A type or namespace that isn't in the workspaces' `registry`, or `reflexr`'s, raises `ValueError`.
- **`emitted=` stays.** It reserves a type to whatever a run caused, which is a handle's causation, not an actor's identity. Folding it in would need a "runs" value that is not an actor.

## Options considered

### What a value names

| Option | A rule's runs | Typed |
|---|---|---|
| **Actors, compared by `participant` (chosen)** | Yes: one participant per rule | Yes |
| Actors, compared by equality | No: each run's `run_id` differs | Yes |
| Participant strings (`"source:artifactr"`) | Yes | No: a typo is a reservation no one can meet |

### Where the check sits

| Option | Who can override it |
|---|---|
| **A fixed check after `authorize` (chosen)** | No one: it is configuration in code, like `emitted=` |
| A decision for `authorize` | The application's hook and grantr's roles, which can't tell a forged bridge event from a real one: both come from an actor allowed to publish |

### Folding `emitted=` in

| Option | Cost |
|---|---|
| **Keep it apart (chosen)** | Two keywords for two kinds of reservation |
| A `runs` value in `publishers` | A value that is not an actor, and a breaking change to `emitted=` |

## Trade-off analysis

Reserving by participant lets one entry cover a source, a system component or a rule's runs, with typed actors as `events=` and `emitted=` take typed classes. Putting the check beneath the hook keeps the policy where ADR-0039 put it: the application's code, which alone resolves clients to actors. The cost ADR-0039 named remains. An application that forgets the bridge's entry leaves forging open, so relayr's wiring should pass it.

## Consequences

- Easier: a bridge's namespace is reserved in one entry, and rules can trust an `artifactr:*` envelope's actor without checking it themselves.
- Easier: an integration's types, such as a webhook's, can be reserved to the source that receives it.
- Harder: an application must never resolve a client to a reserved source. This was true before. Now the library relies on it.
- Revisit: a library-exported entry, once relayr has one to export.

## Action items

1. [x] `Workspaces(publishers=)`, checked at startup and in `publish`, with tests on handles and REST.
2. [ ] relayr's wiring passes `publishers={"artifactr": [SourceActor(name="artifactr")]}` (stackr RFC-0002, phases 3 and 5).
3. [ ] relayr's rules drop their own check of the envelope's actor (stackr RFC-0002, phase 5).
