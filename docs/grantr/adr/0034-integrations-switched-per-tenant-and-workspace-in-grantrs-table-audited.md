# ADR-0034: Integrations switched per tenant and workspace, in grantr's table, audited

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

## Context

lattice's integrations (the trackers, WordCraft, forms, dashboards, mini apps, diagrams, math and Mermaid) each ask one port before they act in a workspace: lattice-core's `Integrations`, whose `is_enabled(tenant_id, workspace_id, key)` answers yes or no ([lattice ADR-0027](../../adr/0027-integrations-switched-per-workspace-through-one-port.md), [lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s O9). relayr's trackers ask the same question through their own `Enabled`. lattice-core declares each integration once, in a registry, `KNOWN`, with its key, its default and a sentence that says what it is; it holds no settings.

The RFC put the adapter, its table, its row-level security and its audit in grantr. portalr's admin already writes through grantr's API, and grantr's audit log already records who changed what, in the same transaction as the change ([ADR-0007](0007-an-append-only-audit-log.md), [ADR-0013](0013-transactions-by-tenant-and-one-audit-log.md)). It left the evaluation, who may switch, the storage and the routes to decide.

## Decision

- **Three levels decide.** The deployment installs some integrations, in its configuration: `Grants(installed=...)`, every integration of the registry if omitted, and a key it doesn't declare is a `ValueError`. That is a ceiling no setting lifts. A tenant's admins and a workspace's admins each turn an integration on or off at their level, or leave it unset. An integration is on in a workspace only if the deployment installs it and the tenant hasn't turned it off; then the workspace's setting decides, or, unset, the tenant's, or, unset too, the integration's default: `installed and tenant != off and (workspace ?? tenant ?? default)`. So an explicit off at the deployment or the tenant is a ceiling nothing below can lift, and a workspace's admin can turn on an integration that is off by default, such as mini apps, unless the tenant turned it off. `grantr.core.effective` is the rule, with no I/O, and a property test holds it to the nearest-set-level reading in every one of its 36 cases.
- **`Grants` is the adapter.** `Grants(integrations=...)` takes the registry, `KNOWN` if omitted, so an application that declares its own integrations passes `registry(*KNOWN.values(), its own)`. `Grants.is_enabled(tenant_id, workspace_id, key, /)` is lattice-core's `Integrations` and, bound, relayr's `Enabled`, by their shape: a root test assigns both and pyright checks them. It checks no one, as `hidden` doesn't: the package that asks is about to act for a caller it checks itself. A key the registry doesn't declare, or the deployment doesn't install, is off without a read; so is every key in a workspace with an empty id; and a store that can't be read turns every key off, with a warning, as a check that can't read the store refuses ([ADR-0015](0015-a-check-writes-nothing.md)).
- **One action switches them: `grantr:manage_integrations`,** in grantr's catalog and in what a workspace's admin holds, beside `grant`, `revoke` and `restrict`. A tenant's owners and admins hold it, as they hold every grantr action but the operators', so they switch on the tenant and in every workspace; a workspace's admin, in that workspace only; and a custom role may hold it, since a custom role holds a workspace admin's actions. A rule can't be granted a role that holds it, as it can't any grantr action ([ADR-0029](0029-a-stored-rule-acts-as-itself-in-its-own-workspace.md)).
- **What an admin reads, and what a member reads:**

  | Read | Requires | Answers |
  |---|---|---|
  | `integrations(tenant, workspace=None, by=...)` | `grantr:manage_integrations` on the tenant, or on the workspace | An `IntegrationState` per integration, in the registry's order: its key, description and default, whether it is installed, the tenant's and the workspace's `IntegrationSetting` (on or off, by whom, when), and whether it is on. On the tenant, `enabled` is what a workspace that sets nothing gets |
  | `integrations_enabled(tenant, workspace, by=...)` | Any library's `open` on the workspace, as `workspaces()` counts them | Each key's answer, for the client that hides what is off |

- **`set_integration(tenant, key, on, workspace=None, by=...)` is a command** like every other: checked first, then one transaction with its audit entry, a new event, `IntegrationSet` (`integration_set`: `workspace`, `None` for the tenant; `key`; `on`, `None` for unset). `on=None` unsets the level, which inherits the one above again. A key the registry doesn't declare, or an empty workspace id, is `Invalid`. A key the deployment doesn't install may be set, and stays off until it is installed. The setting's time is its audit entry's, so the two agree.
- **Only a change is recorded.** Setting a level to what it is set to already, or unsetting what isn't set, writes and records nothing, and returns the state as it is: a `PUT` that is repeated is idempotent, and the log holds one entry per real change, which replay to the stored settings. A property test runs random sequences of settings, repeats and resets, at both levels, in two tenants, and holds the log to exactly that.
- **The settings are a table of their own,** `grantr_integrations` (migration 0006): the tenant, the workspace (`""` for the tenant's own setting, as the other tables avoid nulls in their keys), the key, and the setting as JSON, as an audit entry's body is. Its primary key, `(tenant_id, workspace, key)`, is the read's index. Each `is_enabled` costs two indexed reads of the store, the tenant's rows and the workspace's, each by that key's prefix, on every call: nothing caches them. Deleting a tenant deletes its settings, and a tenant made again with its id starts with none.
- **Row-level security holds on it as on every table** ([ADR-0026](0026-row-level-security-under-the-scoping.md)): migration 0006 enables it and creates `grantr_integrations_tenant`, the same policy, so a transaction reads, changes and adds only its own tenant's settings. A two-tenant test shows a transaction in one tenant neither reads nor writes the other's. The deployment has no settings.
- **The admin API has three routes:**

  | Path | Requires |
  |---|---|
  | `GET /tenants/{tenant}/integrations`; `PUT /tenants/{tenant}/integrations/{key}` | `grantr:manage_integrations` on the tenant |
  | `GET /tenants/{tenant}/workspaces/{workspace}/integrations`; `PUT /tenants/{tenant}/workspaces/{workspace}/integrations/{key}` | `grantr:manage_integrations` on the workspace |
  | `GET /tenants/{tenant}/workspaces/{workspace}/enabled-integrations` | Any library's `open` on the workspace |

  The path names the level, and a `PUT`'s body is `{"on": ...}`: true, false, or null to unset, and required. A workspace's id may hold a `/`; each route ends in segments of its own and a key holds no slash, so a path matches one route however its workspace's id reads, and a test names workspaces `team/integrations` and `team/enabled-integrations`.

- **An external provider only narrows.** The port answers yes or no, so a feature-flag service (issue #361) fits as an `Integrations` of the application's that asks grantr's `is_enabled` first and then the provider, and is on only where both are. It can turn off what grantr's settings leave on, and never turn on what they leave off; its decisions are not in grantr's audit log. lattice builds none.

## Options considered

| Option | For | Against |
|---|---|---|
| **Installed, then the tenant's ceiling, then the nearest set level (chosen)** | A tenant's off holds everywhere in it; a workspace can still turn on what is off by default | Two kinds of level to explain: a ceiling, and an inheritance |
| The nearest set level alone, the tenant's off one more default | One rule | A workspace's admin could turn on what the tenant's admins turned off |
| Every level must say on | Simple | Off by default can never be turned on in one workspace alone |
| **One action, at both levels (chosen)** | Tenant and workspace admins hold it as they hold `grant` | A custom role that holds it switches every integration in its workspace |
| An action per integration | Finer | The catalog would grow with the registry, and every role with it |
| **A table of grantr's (chosen)** | Atomic with its audit entry; row-level security as every table | One more table and migration |
| A settings artifact per workspace | The workspace's own data | People and agents could edit it as data; no audit of who switched |
| **Record only real changes (chosen)** | The log replays exactly; a repeated `PUT` is harmless | A repeat leaves no trace of who repeated it |
| Record every command | Every attempt seen | The log fills with no-ops, and replay must skip them |

## Consequences

- Easier: every integration asks one port, and grantr answers it from the deployment's installation and the tenant's and workspace's settings, with who set each in the audit log. portalr's admin reads and switches them through grantr's API, and its client hides what is off in a workspace.
- Easier: an application declares its own integrations in the registry it passes, and switches them as lattice's.
- Harder: every `is_enabled` is two indexed reads of the store, before each command and model request of an integration's. A cache, if one is needed, belongs to the application's `Integrations`.
- Harder: the registry is configuration, not data: a key removed from it leaves its settings stored and unread, and a key renamed is a new integration.
- To revisit: whether the deployment's installation should be readable through the API, for the admin page to say why an integration is off; `installed` in each state says it already.
