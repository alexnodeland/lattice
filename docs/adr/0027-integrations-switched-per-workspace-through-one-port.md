# ADR-0027: Integrations switched per workspace, through one port

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland
**Implements:** [RFC-0006](../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s shared `Integrations` port (O9, U1), for every integration alike

> **Amended (2026-10-22):** `excalidraw` is off by default, as the other heavier integrations are (mini apps, Mermaid, the crafting apps but WordCraft). Its data layer exists before its canvas, and a workspace's admin turns diagrams on where they are wanted. What this record decides is unchanged.

## Context

Every integration lattice adds must be switchable per workspace: trackers ([RFC-0004](../rfcs/0004-relayr-and-task-trackers.md)), native files ([RFC-0003](../rfcs/0003-native-files-as-artifacts.md)), forms, dashboards and mini apps ([RFC-0005](../rfcs/0005-forms-dashboards-and-mini-apps.md)), rich Markdown, and diagrams (RFC-0006). Two packages already ask a seam of their own before an integration acts: relayr's `Enabled`, a callable `(tenant_id, workspace_id, key) -> bool` with the keys `tracker:plane` and `tracker:vikunja`, and artifactr's forms, whose open pull request asks an `Integrations` with one method, `is_enabled(tenant_id, workspace_id, key)`, and promises it moves to a shared home unchanged. Neither has a store; each application answers it alone.

RFC-0006 proposes the shared port, its store in grantr, audited, and a page in portalr's admin. It names the port's method `enabled` and puts reading every setting and changing one on the port too, and it says it follows whichever ADR settles the port first.

## Decision

- **One port, `lattice_core.integrations.Integrations`, with one method:** `async def is_enabled(tenant_id, workspace_id, key, /) -> bool`. It is the forms' method, unchanged, and its arguments are positional, so a bound `is_enabled` is relayr's `Enabled` too. Neither package's callers change; each adopts the port by importing it.
- **Reading every setting and changing one are grantr's commands,** not the port's: they need a subject to check and to audit, as every grantr command has. The packages that ask only read.
- **The registry is lattice-core's `KNOWN`:** each integration is one declaration, an `Integration` with its key, its default and a sentence for the admin who switches it. An application with its own passes `registry(*KNOWN.values(), mine)`. A key is a name, or a family and a name (`excalidraw`, `files:wordcraft`); a key no one declared is off.
- **Effective is the deployment, the tenant and the workspace together:** `installed and tenant != off and (workspace ?? tenant ?? default)`. The deployment installs integrations in its configuration, as stackr's template does, and one it doesn't install is off everywhere. A tenant's admin and a workspace's admin each set on, off or nothing for their level. Off at the deployment or the tenant is a ceiling nothing below lifts; a level with nothing set inherits the one above, and the default is what an installed integration is where no one has set it. So a workspace's admin can turn on mini apps, which are off by default, unless the tenant turned them off.
- **The store is grantr's:** a table with row-level security in every SQL storage, each change recorded in grantr's audit log in its transaction, and a new action, `grantr:manage_integrations`, held by a tenant's owners and admins and a workspace's admins ([grantr ADR-0034](../grantr/adr/0034-integrations-switched-per-tenant-and-workspace-in-grantrs-table-audited.md)). `Grants` itself answers the port.
- **Checked before access:** artifactr's `Workspaces(gate=...)` runs after the command's target is resolved, so a hidden one is still `NotFound`, and before `authorize`, so off answers `NotEnabled`, never `Forbidden` ([artifactr ADR-0081](../artifactr/adr/0081-a-gate-before-access-integrations-switched-off-answer-not-enabled.md)).
- **No new distribution.** An integration is an extra of the package it extends ([ADR-0026](0026-a-distribution-needs-a-reason-integrations-are-extras.md)); the port and the registry are lattice-core's, the store grantr's, the gate artifactr's and the page portalr's.
- **An external provider may only narrow.** The port answers yes or no, so a feature-flag service (issue #361) is an `Integrations` of the application's that asks grantr's first and then the provider, and is on only where both are. It can never turn on what an admin turned off. None is built.

## Options considered

| Option | For | Against |
|---|---|---|
| **One read-only method, positional, with a registry beside it (chosen)** | relayr's and the forms' seams fit unchanged; asking needs no subject | Changing a setting is grantr's API, not the port's |
| RFC-0006's port: `enabled`, `settings` and `set` | One object does everything | A second name for what the forms already call `is_enabled`; `set` needs a subject the asking packages don't have |
| A flag per integration, in each package's configuration | No store | No admin can switch one per workspace, and nothing is audited |
| A settings artifact per workspace | artifactr already stores it | People could edit it as data, past grantr's checks and audit |
| A feature-flag service | Rollouts and experiments | Another service and account to run; it would decide access, which grantr decides |

## Consequences

- Easier: a new integration is one declaration, and its package asks one port; portalr's page lists it with no change.
- Easier: every switch is in grantr's audit log, beside the grants it sits next to.
- Harder: every gated command and model request asks the store. `Grants.is_enabled` makes two indexed reads, the tenant's settings and the workspace's; an application that asks often caches.
- Revisit: when relayr and artifactr's forms adopt the port, their own seams are deprecated; when a narrowing provider is wanted (#361), it wraps the port.
