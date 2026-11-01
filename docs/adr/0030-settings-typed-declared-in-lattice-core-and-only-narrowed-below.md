# ADR-0030: Settings: typed, declared in lattice-core, and only narrowed below the operator

**Status:** Accepted, amended by [ADR-0038](0038-approval-asked-by-tiers-a-union-resolved-setting-names-and-admin-high-confirmed-by-its-caller.md)
**Date:** 2026-10-22
**Deciders:** Alex Nodeland
**Beside:** [ADR-0027](0027-integrations-switched-per-workspace-through-one-port.md), integrations, which stay switches

## Context

Integrations are booleans, switched per tenant and workspace through one port ([ADR-0027](0027-integrations-switched-per-workspace-through-one-port.md)). Some decisions are values instead: a connected app's hourly limit on tries at code and network calls (artifactr [ADR-0085](../artifactr/adr/0085-connected-apps-an-operators-own-freecad-or-blender-through-a-vetted-mcp-server.md)), and, next, which of an app's tools a workspace offers. Until now these were operator configuration, in code. The owner decided (2026-10-22) that a tenant's and a workspace's admins may change them, with these limits:

- they may only **lower** or **narrow**, never raise;
- a new grant is needed to do it;
- the admin screen is a separate page;
- a value that can't be read **fails closed**;
- the hourly limit is per app within a workspace.

## Decision

- **lattice-core declares settings, in `lattice_core.settings`.** Each `Setting` declares:
  - its key, in the integrations' grammar: a name, or `family:name`, with one colon;
  - its kind: `IntRange(low, high)` or `Subset(universe)`;
  - its default;
  - `lowest`, the lowest tier that may set it: `operator`, `tenant` or `workspace`;
  - a one-sentence description.
  - A setting is never free text and never a secret: no kind holds either. `KNOWN_SETTINGS` is lattice's: `connect-per-hour:freecad` and `connect-per-hour:blender`, each `IntRange(0, 1000)`, default 30, set down to the workspace. The tool name or app is part of the key, never of a free value. Since [artifactr ADR-0089](../artifactr/adr/0089-a-connected-apps-tools-narrowed-per-workspace.md), each app has a `Subset` setting too, `connect-tools:<app>`, the tools a workspace offers. A connected app vetted later adds both of its keys to the registry.
- **Four layers, resolved top down:**
  - the registry's default;
  - the operator's value, in the deployment's configuration, which replaces the default and is checked against the registry as the deployment starts;
  - the tenant's value;
  - the workspace's value.
  - Each layer below the operator may only narrow the one above: `min` for a number, intersection for a subset. Unset leaves a layer as the one above.
- **The ceiling is held three times:**
  - **At write:** a value wider than the layer above is refused (422). The refusal says how wide the value may be and which layer says so: "may be at most 20 here: the tenant's value".
  - **At read:** a stored value is narrowed again by the layers above as they are now. When the operator later lowers the ceiling, the narrower value wins at once; the stored row stays, and an admin's read shows it as `clamped`.
  - **By design:** an operator-only setting can't be written through the REST API at all.
- **A change of the registry never widens a stored value.**
  - A key removed from the registry is never applied. Its row stays and is listed by an admin's read as `unknown`.
  - A number stored under bounds that have since changed is clamped into the new bounds, and is not dropped. Above the new highest, it is lowered to it, so the value can't rise. Below the new lowest, it is raised to it: a registry that raises its lowest is a deliberate widening of what it permits, and it can't be honoured below that. Operators who raise it should expect this.
  - Either way the stored row keeps what was set, and an admin's read flags it `clamped`, showing what applies instead.
  - Names stored in a subset whose universe has since shrunk keep only the names still known.
  - A value of another type is not read, and stands as the setting's floor (`Setting.kept`).
- **Packages ask a `Settings` port,** `value(tenant_id, workspace_id, key)`, each time they act, with no cache. An implementation that can't read its store answers the setting's floor (its lowest number, or no names), so a failure never widens anything. `SettingsDefaults` answers without a store: the operator's value, or the default.
- **grantr stores the tenant and workspace layers** ([grantr ADR-0035](../grantr/adr/0035-settings-narrowed-per-tenant-and-workspace-in-grantrs-table-versioned-audited.md)), and artifactr reads the hourly limit through the port ([artifactr ADR-0087](../artifactr/adr/0087-a-connected-apps-hourly-limit-read-from-settings.md)).

> **Amended (2026-10-29), for [issue #874](https://github.com/alexnodeland/lattice/issues/874):** this ADR's model holds for which kinds an agent's writes apply to directly. The operator widens, and the tiers below only narrow. An application declares `agent-writes:direct`, a `Subset` over its kinds, with artifactr's `direct_writes(types)` and passes it to `registry()` and grantr's `settings=`. It isn't in `KNOWN_SETTINGS`, since kinds register per application. Its default is each type's `write_policy` ([artifactr ADR-0009](../artifactr/adr/0009-write-policies-and-non-blocking-proposals.md)). The operator's configuration may add a kind, such as a native file's. A tenant's or a workspace's admins may only take kinds out, sending them for review in Auto too, and a workspace can't put back what its tenant took out.

## Options considered

| Option | For | Against |
|---|---|---|
| **A typed registry beside integrations (chosen)** | One validator and one rule for narrowing; keeps the integrations' key grammar | A second registry |
| Integrations as keys per tool and per limit | No new machinery | Booleans can't carry a number; a key per tool breaks the one-colon grammar; a workspace may turn on what the tenant left unset |
| Lower tiers may raise up to an operator maximum | More freedom for admins | The owner decided against it: below the operator, only lower |

## Consequences

- Easier: a deployment's limits are tuned per tenant and workspace without a deploy, and can never exceed the operator's.
- Harder: each new value needs a registry entry, and each new connected app needs its own limit key.
- Follow-ups:
  - portalr's Settings page (PR 2);
  - per-tool subsets, `connect-tools:<app>`, with `Connection(offer=)` as the operator's layer (PR 3);
  - hardening the audit log (append-only, or a hash chain), as its own item.
