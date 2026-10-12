# ADR-0012: Every item an access names, and hooks typed by their actor

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

`Grants.hooks(subject_of)` answers the libraries' widened `authorize` and their `hidden`. Lattice RFC-0001 gives artifactr's `Access` a thread and an artifact, and reflexr's a rule, and says grantr reads their fields by name and takes the libraries' actors structurally. It doesn't say what a check is about when an access names more than one item, or how the actor's type reaches the hooks.

## Decision

- **An access is about each item it names,** else its workspace, else, with no workspace, the tenant. One that names a thread and an artifact is allowed only if each is.
- **The hooks are generic in the actor:** `hooks(subject_of: SubjectOf[A]) -> Hooks[A]`. A library's actor type flows from the application's `subject_of` to the hooks it is given, typed, without grantr naming it.

## Options considered

| Option | For | Against |
|---|---|---|
| **Each item named must allow it (chosen)** | Deny by default: an action from a thread on an artifact needs both | Two checks for such an access |
| The most specific item only | One check | Which is more specific is arbitrary, and the other item goes unchecked |
| **`Hooks[A]` (chosen)** | Typed end to end | A type parameter on a small API |
| Actors as `object` | Simpler signatures | `subject_of` would have to narrow its argument itself |

## Consequences

- Easier: the template passes `grants.hooks(subject_of)` to each library's `Workspaces`, typed against its actor.
- Harder: artifactr's `Hidden` has to accept grantr's `Visibility`, which phase 5 types for (grantr RFC-0001's unresolved question).
