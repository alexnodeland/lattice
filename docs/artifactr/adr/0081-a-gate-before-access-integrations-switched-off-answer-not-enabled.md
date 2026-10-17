# ADR-0081: A gate before access: integrations switched off answer NotEnabled

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Records artifactr's part of [lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s O9, the shared switch that [lattice ADR-0027](../../adr/0027-integrations-switched-per-workspace-through-one-port.md) settles.

## Context

Every integration in lattice is switched on or off per workspace, through one port, `lattice_core.integrations.Integrations`, whose store is grantr's ([lattice ADR-0027](../../adr/0027-integrations-switched-per-workspace-through-one-port.md)). Some integrations are artifact types: diagrams are `excalidraw_diagram` artifacts, and native files are artifacts whose `app` names the application that edits them. While such an integration is off, nothing may make or change one of its artifacts, on any surface, and what exists still reads.

Every surface already commits through `Workspace.commit`, which asks the application's two hooks: `hidden`, which answers a restricted item as a missing one ([ADR-0062](0062-restricted-items-left-out-of-every-read.md)), and `authorize`, which answers `Forbidden` ([ADR-0056](0056-access-asked-in-every-workspace-method.md)). Neither fits the switch:

- **`authorize` speaks of grants.** A person refused because diagrams are off would be told `Forbidden`, which says they lack a grant and sends them to an admin who can't grant it.
- **The order matters.** An answer that differs between "off" and "missing" for a hidden diagram tells a person who can't see it that it exists. So hidden comes first, and the switch before grants, so "off" never hints at what a person may do.
- **The switch keys on an artifact, not an action.** `authorize` hears an `Access`, the action and the ids it names, never the artifact's kind, and an edit names only an id.

Until now, `commit` interleaved the two hooks: `hidden` then `authorize` for what the command names, then again for what it implies, a proposal's artifact or a run's thread.

## Decision

- **`NotEnabled(integration)`, a new rejection,** with the code `not_enabled`, the details `{"integration": key}` and the message "`key` is not available in this workspace". REST answers it with 409, as for `invalid_state`: it is a state of the workspace. It is never 403, which speaks of grants.
- **`Workspaces(gate=...)`** takes a `Gate`, `Callable[[Workspace, Command, Versioned[Artifact] | CreateArtifact | None], Awaitable[None]]`, exported from `artifactr.workspace`. Without one, nothing changes.
- **The gate hears what the command changes.** The workspace reads it from storage without asking `authorize`: the artifact an edit or an archive names, or that a proposal is about, as it is now; or the `CreateArtifact` that makes one, a proposal's among them. It is `None` for a command on no artifact, or on one that doesn't exist, which core then refuses as missing. The handle is the committing one, so the gate knows the tenant, the workspace and the actor.
- **The order in `commit`:** the NUL check; the workspace's membership, asked when it was opened; what the command names and implies, each checked against `hidden`, `NotFound` if hidden; the gate; `authorize`, for the command and for what it implies; the allowlist of types; the transaction. So a hidden target is missing whether its integration is on or off, the gate is never asked about it, and a person with no grants, off, is told it is off.
- **`integration_gate(integrations, key_of)`** builds the gate an application needs. `key_of(kind, data)` names the integration that governs an artifact, from its kind and its data as JSON, or `None`: `excalidraw` for an `excalidraw_diagram`, or `files:<app>` from a native file's `app`. While that integration is off, it refuses creating, editing, proposing to create or edit, and accepting a proposal, whatever it proposes. It lets archiving, proposing to archive, and rejecting a proposal through, so people can still tidy up while it is off. A pending proposal stays, and is accepted once it is on again.
- **Accepting is refused whatever it accepts,** a proposed archive too. An answer carries a change out, and may add the reviewer's own `changes` on top, so it is a write of the integration's; it waits for the switch, as the RFC says.
- **Only commands are gated.** Reads, subscriptions and `Workspace.record` are not: facts are the runner's, recording what a run did.
- **artifactr declares no integration key.** The keys are lattice-core's registry; the application, or the package that owns an artifact type, names which one governs what.

## Options considered

### Option A: A gate of its own, after `hidden` and before `authorize` (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one hook and one storage read in `commit`, and the existing checks split in two passes |
| Coverage | Every surface and in-process call, as `authorize` |
| What a refusal says | That the workspace has it off; nothing of grants or hidden items |

**Pros:** each answer means one thing, and the order the RFC sets holds on every surface.
**Cons:** a second hook on `Workspaces`, and a storage read per gated command.

### Option B: The gate inside `authorize`

The application's `authorize` would refuse while an integration is off.

**Cons:** the refusal would be `Forbidden`, which speaks of grants; `authorize` hears no kind, so an edit's integration is unknown to it; and the switch would be asked after a person's grants, so a person with none would be told they lack them.

### Option C: A check from `checks=`

[lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md)'s `checks=`, by command type, could refuse with `NotEnabled`.

**Cons:** checks run after `authorize`, so a person with no grants is told `Forbidden` while it is off; and a check is registered per command type, so every application would repeat the same five registrations. It stays the place for checks of a command's values.

### Option D: The gate before the target is resolved

The gate would be asked first, with only the command.

**Cons:** an edit of a hidden diagram while diagrams are off would answer `NotEnabled`, not `NotFound`, telling a person who can't see it that it exists, and that it is a diagram.

## Trade-off analysis

Option A costs a second hook and an artifact read per gated command, against an answer that tells a person only what is true of the workspace. Option B is free but says the wrong thing, to the wrong person. Option C would put the switch after grants, which is the order the RFC rules out. Option D is simplest in `commit`, and leaks the existence of hidden items, which [ADR-0062](0062-restricted-items-left-out-of-every-read.md) exists to prevent.

## Consequences

- Easier: an application switches an integration's artifacts off per workspace with one `gate=`, on every surface at once.
- Easier: a person is told "not available in this workspace", never that they lack a grant.
- Harder: a hidden implied item now answers `NotFound` before `authorize` hears the command, so a person who may not answer proposals, answering one on a hidden artifact, is told it is missing, not forbidden.
- Harder: the gate is asked before every command, so the `Integrations` it asks answers from a cache; and a switch turned off between the gate and the transaction lets one command through, as a check is not a lock.
- The RFC wrote the gate as `(workspace, actor, command)`. The handle carries its actor, so it is not passed twice; and the gate is given what the command changes, since an edit names only an id, and a gate that read it through the handle would ask `authorize` first.

## Action items

1. [x] `NotEnabled`; `Workspaces(gate=)` and `Gate`; `commit` checking `hidden`, then the gate, then `authorize`; `integration_gate` and `KeyOf`; REST's 409; tests of the order on every storage and every surface, and a property test of the outcomes.
2. [ ] The packages that own diagrams and native files name their keys with `key_of`, and portalr shows `not_enabled` as "Not available in this workspace".
