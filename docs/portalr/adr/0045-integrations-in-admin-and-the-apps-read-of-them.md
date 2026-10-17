# ADR-0045: Integrations in admin, and the app's read of them: each its default where unread, and read again on `not_enabled`

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland
**Amends:** [ADR-0043](0043-markdowns-basics.md), whose add-ons seam this feeds

## Context

lattice switches its integrations (the trackers, WordCraft, forms, dashboards, mini apps, diagrams, math and Mermaid) per workspace, through one port, lattice-core's `Integrations` ([lattice ADR-0027](../../adr/0027-integrations-switched-per-workspace-through-one-port.md)). grantr is its adapter: the deployment installs an integration, and a tenant's admins and a workspace's admins each turn it on or off at their level, or leave it unset. It is on where `installed and tenant != off and (workspace ?? tenant ?? default)`, and every change is in grantr's audit log as `integration_set` ([grantr ADR-0034](../../grantr/adr/0034-integrations-switched-per-tenant-and-workspace-in-grantrs-table-audited.md)). grantr's REST reads a level's integrations for those holding `grantr:manage_integrations` there, sets one, and answers which are on in a workspace for anyone who can open it. artifactr refuses a command an integration that is off needs with `not_enabled` (409), naming the integration.

portalr had no way to switch them, and the app's Markdown took its add-ons from defaults alone: `AddonsProvider` was a seam with nothing on its other side ([ADR-0043](0043-markdowns-basics.md)). This settles where admins switch integrations, what the page shows, how the app reads a workspace's, and what it does when it can't.

## Decision

- **The registry is generated, from lattice-core's.** `moon run portalr:schema` writes `KNOWN`, in its order, to `schemas/integrations.json`, each key, default and sentence (`python -m portalr.integrations`), and a test holds the file to the registry. `moon run client:types` writes it to `web/client/src/generated/integrations.ts` as a constant, `INTEGRATIONS`, which the client's drift test holds to the file, as it holds the other generated types to their documents. An integration added to lattice's registry fails both tests until both commands are run.
- **The client:**
  - `queries.grantr.integrations(tenant, workspace?)` reads a level's integrations; `queries.grantr.enabledIntegrations(tenant, workspace)` reads a workspace's flags; `commands.grantr.setIntegration(tenant, key, on, workspace?)` sets one, `null` to unset it, and answers an `Answer` of its state after.
  - Their keys are under `keys.grantr.integrations(tenant)`, itself under the tenant's grantr key, so `changedIntegrations`, after a setting, makes every read of the tenant's integrations stale, each workspace's flags too: a tenant's setting changes what each of its workspaces gets. A change to access (`changedAccess`) makes them stale as well, since it makes the tenant's grantr key stale.
- **The app reads a workspace's flags once, and keeps them.**
  - The workspace's route prefetches them as it loads, without failing on them, and `WorkspaceAddons` gives its Markdown `mermaid: enabled("markdown:mermaid")` through `AddonsProvider`.
  - The read is fresh for five minutes. After that, the window regaining focus, or the network coming back, reads it again, as TanStack Query does a stale read: a read still fresh isn't read on focus. A command artifactr refuses as `not_enabled` makes it stale at once (`stale.refusal`): the server saying an integration is off is the sign that the page's flags are out of date. `Stream` hears its refusals through `onRefused`, as it hears its live events through `onLiveEvent`, and `WorkspaceStreams` makes the flags stale from either.
- **Where the flags can't be read, each integration is its default: the app fails closed, per integration.** Unread, or failed (unreachable, a 5xx, a network error), `useEnabled`'s `enabled(key)` answers the registry's default for each key, from the generated module, and what was last read once a read has succeeded. So mini apps and Mermaid, off by default, stay off, and forms, on by default, stay on. A failed read never fails the page. Turning every integration off on a failed read was the other choice: safer for what is on by default, but a blip in grantr would hide forms and dashboards from every workspace at once. The server still checks every command: what the app shows is no permission.
- **A command refused as `not_enabled` is said as "Not available in this workspace."** `ui`'s chat parts say why a command wasn't done from the store's answer, which `Sent` now carries; that refusal speaks of the workspace, never of the person's grants, as the RFC asked.
- **admin's Integrations page, `/t/$tenant/integrations`:**
  - It is on the rail after Access, before Audit, where grantr allows `grantr:manage_integrations` on the tenant, and its route is not found elsewhere, as every area of admin is ([ADR-0023](0023-admins-shell-and-home.md)). admin admits only a tenant's owners and admins, who hold it on the tenant: a workspace's admin, who holds it on their workspace alone, switches nothing here.
  - The level is chosen at the top: the tenant, or one of the tenant's workspaces as artifactr lists them, as Runs and Usage list them. The address keeps it, `?workspace=`, read as a workspace's name grantr takes or the tenant otherwise; a workspace the tenant doesn't have is said.
  - The list is `ui`'s `IntegrationList`, in the registry's order: each integration's name, from its sentence's start, its key and its sentence; a switch, named by the integration and described by its state in words; a badge, "On" a filled circle and "Off" an outlined square, so no state is told by colour alone; where the state comes from: "Default", "Inherited from the tenant", "Set here", "Off for the tenant" or "Not installed in this deployment"; and who set it at this level, as people are named in admin ([ADR-0038](0038-people-by-email.md)), and when, with "See the audit log", filtered to integrations switched, where the reader may read the log.
  - The tenant's off and the deployment's not installing are ceilings: the switch is disabled, with the reason beside it. A level with a setting of its own offers "Back to inherited" (on the tenant, "Back to the default"), which unsets it.
  - A change is not optimistic, as no change in admin is: the switch is disabled while it saves, its badge says "Saving…", and once grantr answers, the page reads the level again and says what came of it in a polite status, or why it wasn't done in an alert.
- **The kit:**
  - `IntegrationList` is an `ItemTable`, a table from 640 pixels and cards below, so a phone gets the same switches. Its tests run axe in both schemes, wide and narrow.
  - `integrations.screenshot.test.tsx` pins every state, saving included, wide and narrow, in colour-blind mode and under forced colours, in each scheme, against Linux baselines made in CI ([ADR-0019](0019-the-kits-look.md), [ADR-0036](0036-the-chart-theme-and-colour-blind-mode.md)).
  - `Switch`, under forced colours, takes the system's colours: on is the highlight's track with its text's thumb, off a framed track with the text's thumb, and disabled the grey's. A high-contrast mode drops the fills its state was told by, and its thumb with them.

## Options considered

| Option | For | Against |
|---|---|---|
| **Each integration its default where unread (chosen)** | Off by default stays off; a blip hides nothing that is on by default | An integration a workspace turned off shows while grantr can't be read; the server refuses its commands |
| Every integration off where unread | Nothing shows that might be off | A blip in grantr hides forms and dashboards everywhere |
| **Read once, fresh five minutes, again on `not_enabled` (chosen)** | One read a workspace; a change reaches a page by focus or by its first refused command | A change can take five minutes to show in a page left open and unused |
| Read on every focus | A change shows sooner | A read each time the window is focused, for what changes rarely |
| Pushed over the stream | At once | artifactr's log would carry grantr's settings, which aren't its events |
| **The registry generated from Python (chosen)** | One source, held by two drift tests | Two commands to run when an integration is added |
| Defaults written in the client by hand | No generation | Drift from lattice's registry, unseen |
| **One page, the level chosen at its top (chosen)** | The tenant and every workspace side by side in one place; admin has no workspace routes | A workspace's admin can't use it |
| A workspace's own settings page in the app | Workspace admins can switch their own | A settings area in the app, which has none |

## Consequences

- Easier: a tenant's owners and admins switch every integration, on the tenant or in any workspace, see where each state comes from, and who set it; the app's Markdown follows what is on, and a refusal says the integration is off here.
- Easier: an integration added to lattice's registry reaches the page from grantr, and the app's defaults from the generated module, once `moon run portalr:schema client:types` is run.
- Harder: what a member sees can be up to five minutes behind a change, until the window is focused again or a command is refused.
- Harder: `app`'s initial bundle grows by about 3 kB (gzip), mostly TanStack Query's observer, which the workspace's route now needs and which a shared chunk carries instead of a route's own; its total grows by 0.2 kB. admin's grows by 2.6 kB initially and 7.3 kB in all. Both are within their budgets ([ADR-0040](0040-scenarios-against-a-generated-application-and-size-budgets.md)).
- To revisit: a page for a workspace's admins, who hold the action on their workspace but can't open admin.
